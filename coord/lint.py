"""Lint a coordination repository: every violation of PROTOCOL.md section 6, with the commit that made it.

    python -m coord.lint --repo <repository>

Exit code 0 when there is nothing to fix, 3 when there is at least one error. Warnings do not fail.
"""
from __future__ import annotations

import argparse
import json
import sys

from coord import gitlog, state as state_mod
from coord.parse import Finding

FIX = {
    "V01": "past entries are never edited: append a new entry (a PROPOSE with 'supersedes', a new RECEIPT, a DISSENT)",
    "V02": "the agent named in 'by' commits its own entries",
    "V03": "the recipient appends a RECEIPT that repeats the anchors",
    "V04": "the recipient appends a new RECEIPT with what it actually received; the release stays blocked until they match",
    "V05": "collect the missing consents, then append a new DECIDE",
    "V06": "remove one block of the cycle (UNBLOCK, with its consents)",
    "V07": "UNBLOCK it, or point 'on' at what is really awaited",
    "V08": "give the second agent an id of its own",
    "V09": "append at the end of the log: order comes from commits, not from position or as_of",
    "V10": "save the file as UTF-8 and append a corrected entry",
    "V11": "cite the rule and the outcome the rule file gives, or 'rule: none' with ESCALATE_TO_HUMAN",
    "unparsed": "append a well-formed entry; until then the state is degraded",
    "malformed": "append a well-formed entry; until then the state is degraded",
    "invalid": "append an entry the rules accept",
    "ambiguous": "the agent appends one answer after the merge",
}


def line(f: Finding, sha_of: dict[int, str]) -> str:
    sha = f" ({sha_of[f.commit_index][:12]})" if f.commit_index in sha_of else ""
    cites = f" [{', '.join(f.cites)}]" if f.cites else ""
    label = f.cls if f.name == f.cls else f"{f.cls} {f.name}"
    return f"{'ERROR' if f.severity == 'error' else 'WARN '} {label}: commit {f.commit_index}{sha}, {f.target}: {f.detail}{cites}"


def report(st, sha_of: dict[int, str] | None = None) -> str:
    sha_of = sha_of or {}
    errors = st.errors
    warnings = [f for f in st.findings if f.severity == "warn"]
    head = (f"lint: {'FAILED' if errors else 'OK'} - {len(errors)} error(s), {len(warnings)} warning(s) in "
            f"{st.commits} commit(s), as of commit {st.as_of.get('commit_index')} ({st.as_of.get('committed_utc')})")
    out = [head]
    for f in st.findings:
        out.append(line(f, sha_of))
        if f.severity == "error" and f.cls in FIX:
            out.append(f"      fix: {FIX[f.cls]}")
    if st.degraded:
        out.append("state DEGRADED: every asserting status is TO_CONFIRM and the release gate is BLOCKED")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coord.lint", description="Lint a coordination repository.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", help="directory with the rule files (default: rules/)")
    ap.add_argument("--json", action="store_true", help="findings as JSON, commits cited by index only")
    ap.add_argument("--no-sha", action="store_true", help="cite commits by index only")
    a = ap.parse_args(argv)
    try:
        from coord.rules import load
        log = gitlog.read(a.repo)
        st = state_mod.derive(log, load(a.rules))
    except (gitlog.LogError, gitlog.fixture.GitError, OSError, ValueError) as exc:
        sys.stdout.buffer.write(f"lint: FAILED - the repository could not be read: {exc}\n".encode("utf-8"))
        return 2
    if a.json:
        text = json.dumps({"as_of": st.as_of, "ok": not st.errors, "degraded": st.degraded,
                           "findings": [f.as_dict() for f in st.findings]}, indent=2, sort_keys=True, ensure_ascii=False)
    else:
        text = report(st, {} if a.no_sha else {c.index: c.sha for c in log.commits})
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 3 if st.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
