"""Render a story (list of events) as a git history: one `COORD.md` snapshot per commit, written as a
git fast-import stream with fixed dates and fictitious identities.

Rendering knows nothing about state: it only writes what each event says was written. Style options
(the `style` key of an event) change how an entry looks, never what it means; the stress profile of
the generator uses them, the standard profile does not.
"""
from __future__ import annotations

import json
from datetime import timedelta

from corpus.events import parse_utc, tz_delta

FIELD_ORDER = ("by", "to", "refs", "on", "scope", "supersedes", "resource", "class", "due", "rule", "outcome",
               "anchors", "as_of", "text", "note")
LIST_FIELDS = ("to", "refs")


def mojibake(s: str) -> str:
    """UTF-8 bytes read as Latin-1: the classic corrupted accent."""
    return s.encode("utf-8").decode("latin-1")


def _value(key: str, value, style: dict) -> str:
    if key in LIST_FIELDS:
        return style.get("sep", ", ").join(value)
    if key == "anchors":
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if key == "as_of" and style.get("as_of") == "local":
        return value[:16].replace("T", " ")
    return str(value)


def _key(key: str, style: dict) -> str:
    k = {"cap": key.capitalize(), "upper": key.upper()}.get(style.get("keys", ""), key)
    return f"**{k}**" if style.get("bold") else k


def render_entry(entry: dict, style: dict | None = None, corrupt: bool = False) -> list[str]:
    style = style or {}
    etype = entry["type"].lower() if style.get("heading") == "lower" else entry["type"]
    head = {"id_first": f"### {entry['id']} {etype}", "colon": f"### {etype}: {entry['id']}",
            "h4": f"#### {etype} {entry['id']}"}.get(style.get("heading", ""), f"### {etype} {entry['id']}")
    keys = [k for k in FIELD_ORDER if k in entry]
    for a, b in style.get("swap", []):
        if a < len(keys) and b < len(keys):
            keys[a], keys[b] = keys[b], keys[a]
    lines = [head]
    for k in keys:
        v = _value(k, entry[k], style)
        if corrupt and k in ("text", "note"):
            v = mojibake(v)
        lines.append(f"{style.get('bullet', '-')} {_key(k, style)}: {v}".rstrip(" "))
    return lines


def agent_line(a: dict) -> str:
    return f"- {a['id']} | {a['name']} | {a['email']} | {a['role']}"


def file_json(obj: dict) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


class _Doc:
    """The repository content at one commit."""

    def __init__(self):
        self.title = ""
        self.agents: list[str] = []
        self.blocks: list[tuple[str, list[str]]] = []   # (entry id, rendered lines)
        self.files: dict[str, bytes] = {}
        self.eol = "\n"

    def copy(self) -> "_Doc":
        d = _Doc()
        d.title, d.agents, d.eol = self.title, list(self.agents), self.eol
        d.blocks, d.files = [(i, list(l)) for i, l in self.blocks], dict(self.files)
        return d

    def text(self) -> bytes:
        lines = [f"# COORD - {self.title}", "", "protocol: coord/1", "", "## Agents", "", *self.agents, "", "## Log"]
        for _, block in self.blocks:
            lines += ["", *block]
        return (self.eol.join(lines) + self.eol).encode("utf-8")

    def snapshot(self) -> dict[str, bytes]:
        return {"COORD.md": self.text(), **self.files}


def _apply(doc: _Doc, ev: dict, entries: dict[str, dict], styles: dict[str, dict]) -> None:
    op = ev["op"]
    if op == "init":
        doc.title = ev["team"]["title"]
        doc.agents = [agent_line(a) for a in ev["agents"]]
        doc.eol = "\r\n" if (ev.get("style") or {}).get("eol") == "crlf" else "\n"
    elif op in ("join", "dup_agent"):
        doc.agents.append(agent_line(ev["agent"]))
    elif op == "entry":
        e, style = ev["entry"], ev.get("style") or {}
        entries[e["id"]], styles[e["id"]] = e, style
        block = (e["id"], render_entry(e, style, corrupt=bool(ev.get("mojibake"))))
        if ev.get("insert_before"):
            at = [i for i, _ in doc.blocks].index(ev["insert_before"])
            doc.blocks.insert(at, block)
        else:
            doc.blocks.append(block)
        if e["type"] == "HANDOFF":
            doc.files[f"handoffs/{e['id']}.json"] = file_json({"schema": "coord/handoff/1", "id": e["id"], "by": e["by"],
                                                              "to": e["to"][0], "as_of": e["as_of"], "anchors": e["anchors"]})
        elif e["type"] == "RECEIPT":
            doc.files[f"receipts/{e['id']}.json"] = file_json({"schema": "coord/receipt/1", "id": e["id"], "handoff": e["refs"][0],
                                                              "by": e["by"], "as_of": e["as_of"], "anchors": e["anchors"]})
    elif op == "tamper":
        target, ch = ev["target"], ev["change"]
        if target == "header":
            doc.title = ch["value"]
        elif target.startswith("agent:"):
            aid = target.split(":", 1)[1]
            for i, line in enumerate(doc.agents):
                if line.startswith(f"- {aid} |"):
                    doc.agents[i] = line.rsplit("|", 1)[0] + "| " + ch["value"]
                    break
        else:
            at = [i for i, _ in doc.blocks].index(target)
            e = dict(entries[target])
            if ch["kind"] == "delete":
                del doc.blocks[at]
            elif ch["kind"] == "file":
                path = f"{'handoffs' if e['type'] == 'HANDOFF' else 'receipts'}/{target}.json"
                obj = json.loads(doc.files[path].decode("utf-8"))
                obj["anchors"] = ch["anchors"]
                doc.files[path] = file_json(obj)
            else:
                if ch["kind"] == "retype":
                    e["type"] = ch["type"]
                    if ch["type"] == "ACK" and "text" in e:
                        e["note"] = e.pop("text")
                else:
                    e[ch["field"]] = ch["value"]
                doc.blocks[at] = (target, render_entry(e, styles[target]))
    elif op != "merge":
        raise ValueError(f"unknown op {op}")


def snapshots(events: list[dict]) -> list[dict[str, bytes]]:
    """Repository content after each event, in order."""
    docs: dict[int, _Doc] = {}
    entries: dict[str, dict] = {}
    styles: dict[str, dict] = {}
    born: dict[str, str] = {}   # entry id -> UTC of the commit that added it
    out = []
    for ev in events:
        n, parents = ev["n"], ev["parents"]
        doc = docs[parents[0]].copy() if parents else _Doc()
        if ev["op"] == "merge":
            others = [docs[p] for p in parents[1:]]
            shared = set.intersection(*({i for i, _ in d.blocks} for d in [doc, *others]))
            keep = 0
            while keep < len(doc.blocks) and doc.blocks[keep][0] in shared:
                keep += 1
            have = {i for i, _ in doc.blocks}
            for other in others:
                doc.blocks += [(i, list(lines)) for i, lines in other.blocks if i not in have]
                have |= {i for i, _ in other.blocks}
                for path, data in other.files.items():
                    doc.files.setdefault(path, data)
                doc.agents += [line for line in other.agents if line not in doc.agents]
            if (ev.get("style") or {}).get("merge_order") != "branch":
                doc.blocks[keep:] = sorted(doc.blocks[keep:], key=lambda blk: born[blk[0]])
        else:
            _apply(doc, ev, entries, styles)
            if ev["op"] == "entry":
                born[ev["entry"]["id"]] = ev["utc"]
        docs[n] = doc
        out.append(doc.snapshot())
    return out


def _ident(agent: dict, utc: str, corrupt_name: bool = False) -> bytes:
    when = parse_utc(utc)
    off = tz_delta(agent["tz"])
    minutes = int(off / timedelta(minutes=1))
    tz = f"{'-' if minutes < 0 else '+'}{abs(minutes) // 60:02d}{abs(minutes) % 60:02d}"
    name = mojibake(agent["name"]) if corrupt_name else agent["name"]
    return f"{name} <{agent['email']}> {int(when.timestamp())} {tz}".encode("utf-8")


def _subject(ev: dict) -> str:
    if ev["op"] == "entry":
        return f"coord: {ev['entry']['type']} {ev['entry']['id']}"
    return {"init": "coord: open the coordination document", "join": "coord: agent joins", "dup_agent": "coord: agents",
            "tamper": "coord: tidy up", "merge": "coord: merge concurrent entries"}[ev["op"]]


def stream(events: list[dict], start: int = 1, *, ref: str = "refs/heads/main", select: set[int] | None = None,
           external: dict[int, str] | None = None) -> bytes:
    """A git fast-import stream for the story. With `start` > 1 only the commits from event `start` on are
    written, to be imported on top of a repository that already holds the earlier ones (their parent must
    be the current tip of `main`). `select` keeps only some events, `ref` is the branch they are written to,
    and `external` names the commits (a branch, usually) that stand for parents not written in this stream."""
    agents: dict[str, dict] = {}
    for ev in events:
        if ev["op"] == "init":
            agents.update({a["id"]: a for a in ev["agents"]})
        elif ev["op"] == "join":
            agents[ev["agent"]["id"]] = ev["agent"]
    snaps = snapshots(events)
    out: list[bytes] = []
    written: set[int] = set()
    for ev, snap in zip(events, snaps):
        if ev["n"] < start or (select is not None and ev["n"] not in select):
            continue
        who = ev.get("identity") or agents[ev["commit_by"]]
        ident = _ident(who, ev["utc"], corrupt_name=bool(ev.get("mojibake_author")))
        msg = _subject(ev).encode("utf-8")
        out += [f"commit {ref}".encode(), f"mark :{ev['n']}".encode(), b"author " + ident,
                b"committer " + ident, f"data {len(msg)}".encode(), msg]
        for k, p in enumerate(ev["parents"]):
            if p in written:
                parent = f":{p}"
            elif external is not None:
                parent = external[p]
            elif k == 0 and p == start - 1 and ev["n"] == start:
                parent = "refs/heads/main^0"
            else:
                raise ValueError("an incremental stream must continue from the tip")
            out.append(f"{'from' if k == 0 else 'merge'} {parent}".encode())
        written.add(ev["n"])
        before = snaps[ev["parents"][0] - 1] if ev["parents"] else {}
        for path in sorted(set(before) - set(snap)):
            out.append(f"D {path}".encode())
        for path in sorted(snap):
            if before.get(path) != snap[path]:
                out += [f"M 100644 inline {path}".encode(), f"data {len(snap[path])}".encode(), snap[path]]
        out.append(b"")
    return b"\n".join(out) + b"\n"
