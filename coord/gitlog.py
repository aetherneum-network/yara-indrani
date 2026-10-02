"""Read a coordination history from `git log` - read-only.

One `git log -p` call gives every commit with its author, its committer time and the full text of the
files it changed. From that, and nothing else, this module rebuilds what each commit *added*: the
entries, the agent lines, the handoff and receipt files - and what it changed that it should not have.

Nothing here decides a state. It only reports who wrote what, in which commit, and what cannot be read.
"""
from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, field
from pathlib import Path

from coord import fixture
from coord.parse import AgentLine, Doc, Entry, Finding, looks_corrupted, parse_doc

DOC = "COORD.md"
_PROTOCOL_FILE = re.compile(r"^(COORD\.md|handoffs/[^/]+\.json|receipts/[^/]+\.json)$")
_HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_FORMAT = "--format=%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%ct%x1f%s%x1f"


class LogError(RuntimeError):
    """The output of git log is not what this reader understands. It stops instead of guessing."""


@dataclass
class Commit:
    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    committed: int
    subject: str
    files: dict[str, bytes] = field(default_factory=dict)   # protocol files after this commit
    index: int = 0                                          # 1-based position in log order


@dataclass
class Log:
    commits: list[Commit]
    entries: list[Entry]                     # well-formed entries, in log order
    roster: dict[str, AgentLine]             # first agent line for each id
    roster_since: dict[str, int]             # agent id -> commit index of its first line
    findings: list[Finding]
    ancestors: dict[int, frozenset[int]]     # commit index -> indices of the commits it descends from
    degraded: list[str]                      # reasons why something in the log could not be read
    head_files: dict[str, bytes]
    first_files: dict[str, tuple[int, bytes]]   # path -> (commit index, content when first added)

    @property
    def head(self) -> Commit | None:
        return self.commits[-1] if self.commits else None


# -- git log -> commits -----------------------------------------------------------------------------------

def _path_of(diff_line: bytes) -> str:
    body = diff_line[len(b"diff --git "):].decode("utf-8", "replace")
    if body.startswith('"'):
        return body
    half = (len(body) - 1) // 2
    return body[2:half]


def _parse_log(out: bytes) -> list[tuple[Commit, dict[str, bytes | None]]]:
    lines = out.split(b"\n")
    result: list[tuple[Commit, dict[str, bytes | None]]] = []
    i, n = 0, len(lines)
    changes: dict[str, bytes | None] = {}
    while i < n:
        ln = lines[i]
        if ln.startswith(b"\x1e"):
            p = ln[1:].split(b"\x1f")
            if len(p) < 6:
                raise LogError("unreadable commit header")
            d = [x.decode("utf-8", "replace") for x in p]
            changes = {}
            result.append((Commit(d[0], tuple(d[1].split()), d[2], d[3], int(d[4]), d[5]), changes))
            i += 1
        elif ln.startswith(b"diff --git "):
            if not result:
                raise LogError("diff before any commit")
            path, deleted, i = _path_of(ln), False, i + 1
            new: list[bytes] = []
            newline_at_end, hunks = True, 0
            while i < n and not lines[i].startswith((b"diff --git ", b"\x1e")):
                h = lines[i]
                m = _HUNK.match(h)
                if m:
                    hunks += 1
                    old_left = int(m.group(2) or 1)
                    new_left = int(m.group(4) or 1)
                    if hunks > 1 or int(m.group(3)) > 1:
                        raise LogError(f"partial diff for {path}")
                    i += 1
                    last = b""
                    while (old_left > 0 or new_left > 0) and i < n:
                        c, body = lines[i][:1], lines[i][1:]
                        if c == b" ":
                            old_left, new_left = old_left - 1, new_left - 1
                            new.append(body)
                        elif c == b"+":
                            new_left -= 1
                            new.append(body)
                        elif c == b"-":
                            old_left -= 1
                        elif c == b"\\":
                            if last in (b"+", b" "):
                                newline_at_end = False
                        else:
                            raise LogError(f"unexpected line in the diff of {path}")
                        last = c if c != b"\\" else last
                        i += 1
                    if i < n and lines[i].startswith(b"\\"):
                        if last in (b"+", b" "):
                            newline_at_end = False
                        i += 1
                    continue
                if h.startswith(b"deleted file mode") or h == b"+++ /dev/null":
                    deleted = True
                elif h.startswith(b"Binary files "):
                    new, hunks = [b"\x00"], 1
                i += 1
            changes[path] = None if deleted else (b"\n".join(new) + (b"\n" if newline_at_end and new else b""))
        else:
            i += 1
    return result


def _log_order(commits: list[Commit]) -> list[Commit]:
    """Parents before children; among commits with no order between them, earlier committer time first."""
    by_sha = {c.sha: c for c in commits}
    pending = {c.sha: sum(1 for p in c.parents if p in by_sha) for c in commits}
    children: dict[str, list[str]] = {c.sha: [] for c in commits}
    for c in commits:
        for p in c.parents:
            if p in by_sha:
                children[p].append(c.sha)
    ready = [(c.committed, c.sha) for c in commits if pending[c.sha] == 0]
    heapq.heapify(ready)
    out = []
    while ready:
        _, sha = heapq.heappop(ready)
        out.append(by_sha[sha])
        for ch in children[sha]:
            pending[ch] -= 1
            if pending[ch] == 0:
                heapq.heappush(ready, (by_sha[ch].committed, ch))
    if len(out) != len(commits):
        raise LogError("the commit graph is not a DAG")
    for i, c in enumerate(out, start=1):
        c.index = i
    return out


def read_commits(repo: str | Path, ref: str = "main") -> list[Commit]:
    """Every commit reachable from `ref`, in log order, each with the protocol files as they were after it."""
    fixture.require_git()
    cp = fixture.git(["-c", "core.quotePath=false", "-c", "log.showRoot=true", "-c", "i18n.logOutputEncoding=UTF-8",
                      "log", "--topo-order", "--reverse", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
                      "--diff-merges=first-parent", "-p", "-U1000000", _FORMAT, ref, "--"],
                     git_dir=fixture.git_dir_of(repo))
    parsed = _parse_log(cp.stdout)
    by_sha: dict[str, Commit] = {}
    for commit, changes in parsed:
        files = dict(by_sha[commit.parents[0]].files) if commit.parents and commit.parents[0] in by_sha else {}
        for path, content in changes.items():
            if not _PROTOCOL_FILE.match(path):
                continue
            if content is None:
                files.pop(path, None)
            else:
                files[path] = content
        commit.files = files
        by_sha[commit.sha] = commit
    return _log_order([c for c, _ in parsed])


# -- commits -> what each one added -------------------------------------------------------------------------

def _entry_of(path: str) -> str:
    return path.rsplit("/", 1)[1][:-len(".json")]


def extract(commits: list[Commit]) -> Log:
    """Entries in log order with their commit and author, and every structural finding (V01, V02, V08, V09,
    V10, unparsed, malformed)."""
    findings: list[Finding] = []
    degraded: list[str] = []
    entries: list[Entry] = []
    registry: dict[str, Entry] = {}
    roster: dict[str, AgentLine] = {}
    roster_since: dict[str, int] = {}
    duplicated: set[str] = set()
    docs: dict[str, Doc | None] = {}
    cache: dict[bytes, Doc] = {}
    index_of = {c.sha: c.index for c in commits}
    by_sha = {c.sha: c for c in commits}
    ancestors: dict[int, frozenset[int]] = {}
    first_files: dict[str, tuple[int, bytes]] = {}
    repeated: set[tuple[str, str]] = set()

    for c in commits:
        known_parents = [p for p in c.parents if p in by_sha]
        anc: set[int] = set()
        for p in known_parents:
            anc |= ancestors[index_of[p]] | {index_of[p]}
        ancestors[c.index] = frozenset(anc)
        # handoff and receipt files: added once, never changed
        for p in known_parents:
            for path, old in by_sha[p].files.items():
                if path != DOC and c.files.get(path) != old and not any(
                        by_sha[q].files.get(path) == c.files.get(path) for q in known_parents if q != p):
                    findings.append(Finding("V01", c.index, _entry_of(path), f"{path} changed or removed after it was written",
                                            (path,)))
                    if _entry_of(path) in registry:
                        registry[_entry_of(path)].doubt.add("modified")
        for path, content in c.files.items():
            if path != DOC and path not in first_files:
                first_files[path] = (c.index, content)

        data = c.files.get(DOC)
        parent_docs = [docs[p] for p in known_parents if docs.get(p) is not None]
        if data is None:
            docs[c.sha] = None
            if parent_docs:
                findings.append(Finding("V01", c.index, "header", f"{DOC} removed"))
                degraded.append(f"c{c.index}: {DOC} removed")
            continue
        doc = cache.get(data)
        if doc is None:
            doc = cache[data] = parse_doc(data)
        docs[c.sha] = doc
        merge = len(known_parents) > 1

        if parent_docs and all(doc.header != pd.header for pd in parent_docs):
            findings.append(Finding("V01", c.index, "header", "the header of the document changed"))
        # agent lines
        now = [a.raw for a in doc.agents]
        before = {a.raw: a for pd in parent_docs for a in pd.agents}
        replaced: set[str] = set()
        for raw, a in before.items():
            if raw not in now:
                findings.append(Finding("V01", c.index, f"agent:{a.id}", "an agent line changed or was removed"))
                replaced.add(a.id)
        for a in doc.agents:
            if a.raw in before:
                continue
            if a.id not in roster:
                roster[a.id], roster_since[a.id] = a, c.index
            elif a.id not in replaced and roster[a.id].raw != a.raw:
                findings.append(Finding("V08", c.index, f"agent:{a.id}",
                                        f"id '{a.id}' already belongs to another agent line (first seen at c{roster_since[a.id]})"))
                duplicated.add(a.id)
            if looks_corrupted(a.raw):
                findings.append(Finding("V10", c.index, f"agent:{a.id}", "agent line with corrupted accents"))
        # blocks that are not entries
        old_unparsed = {u.raw for pd in parent_docs for u in pd.unparsed}
        for u in doc.unparsed:
            if u.raw not in old_unparsed:
                findings.append(Finding("unparsed", c.index, f"line:{u.line}", u.reason))
                degraded.append(f"c{c.index}: {u.reason} (line {u.line})")
        # entries
        parent_raw: dict[str, set[str]] = {}
        for pd in parent_docs:
            for e in pd.entries:
                parent_raw.setdefault(e.id, set()).add(e.raw)
        here = {e.id: e for e in reversed(doc.entries)}     # first occurrence wins
        for eid, raws in parent_raw.items():
            if eid not in here:
                findings.append(Finding("V01", c.index, eid, "a past entry was removed"))
            elif here[eid].raw not in raws:
                findings.append(Finding("V01", c.index, eid, "a past entry was rewritten in place", (f"{DOC}:{here[eid].line}",)))
            else:
                continue
            if eid in registry:
                registry[eid].doubt.add("modified")
        inherited_seen = 0
        inherited_total = sum(1 for e in here.values() if e.id in parent_raw)
        seq = 0
        for e in doc.entries:
            if here[e.id] is not e:     # a second block with an id already used in this document
                if (e.id, e.raw) not in repeated:
                    repeated.add((e.id, e.raw))
                    findings.append(Finding("malformed", c.index, e.id, f"entry id {e.id} appears twice in the document",
                                            (f"{DOC}:{e.line}",)))
                    degraded.append(f"c{c.index}: entry id {e.id} appears twice")
                continue
            if e.id in parent_raw:
                inherited_seen += 1
                continue
            known = registry.get(e.id)
            if known is not None:
                if known.commit_index in ancestors[c.index]:
                    if known.raw != e.raw:      # removed earlier, now back with different content
                        findings.append(Finding("V01", c.index, e.id, "a past entry was rewritten in place"))
                        known.doubt.add("modified")
                else:
                    findings.append(Finding("malformed", c.index, e.id, "entry id already used on another branch"))
                    degraded.append(f"c{c.index}: entry id {e.id} used twice")
                continue
            seq += 1
            e.commit_index, e.seq, e.author_email = c.index, seq, c.author_email
            registry[e.id] = e
            if e.problems:
                findings.append(Finding("malformed", c.index, e.id, "; ".join(e.problems), (f"{DOC}:{e.line}",)))
                degraded.append(f"c{c.index}: entry {e.id} is malformed")
                continue
            for cls, detail in e.warnings:
                findings.append(Finding(cls, c.index, e.id, detail))
            if not merge and inherited_seen < inherited_total:
                findings.append(Finding("V09", c.index, e.id, "inserted above existing entries instead of appended",
                                        (f"{DOC}:{e.line}",)))
            agent = roster.get(e.by)
            if agent is not None and agent.email != c.author_email:
                findings.append(Finding("V02", c.index, e.id,
                                        f"'by: {e.by}' but the commit author is {c.author_email}", (f"{DOC}:{e.line}",)))
                e.doubt.add("author")
            if e.by in duplicated:
                e.doubt.add("duplicate_agent")
            if looks_corrupted(e.raw):
                findings.append(Finding("V10", c.index, e.id, "text with corrupted accents", (f"{DOC}:{e.line}",)))
            entries.append(e)
        if looks_corrupted(c.author_name):
            findings.append(Finding("V10", c.index, "author", "commit author name with corrupted accents"))

    head = commits[-1] if commits else None
    findings = list(dict.fromkeys(findings))
    return Log(commits=commits, entries=entries, roster=roster, roster_since=roster_since, findings=findings,
               ancestors=ancestors, degraded=degraded, head_files=dict(head.files) if head else {},
               first_files=first_files)


def read(repo: str | Path, ref: str = "main") -> Log:
    return extract(read_commits(repo, ref))
