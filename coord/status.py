"""The state of a coordination in one command, from the log.

    python -m coord.status --repo <repository>

Every answer names the commit it was read at (`as_of`): ask again after a new commit and the `as_of`
moves with it. Nothing is cached and nothing is remembered between two calls.
"""
from __future__ import annotations

import argparse
import json
import sys

from coord import gitlog, state as state_mod
from coord.parse import parse_doc
from coord.rules import load

HUMAN = "a human"
THIRD = "any third agent"


def pending(st) -> dict[str, list[str]]:
    """Who the coordination is waiting for, and for what."""
    out: dict[str, list[str]] = {}

    def add(agent: str, what: str) -> None:
        out.setdefault(agent, []).append(what)

    d, s = st.details, st.status
    for pid, p in d["proposals"].items():
        status = s["proposals"][pid]
        if status in ("DECIDED", "SUPERSEDED"):
            continue
        if status == state_mod.TO_CONFIRM:
            add(HUMAN, f"confirm {pid} (it rests on a doubtful entry)")
        elif status == "ALIGNED":
            add(p["by"], f"DECIDE {pid}")
        else:
            for a in p["missing"]:
                add(a, f"ACK {pid}")
    for kind, verb in (("blocks", "UNBLOCK"), ("freezes", "LIFT")):
        for gid, g in d[kind].items():
            if s[kind][gid] in ("REMOVED", "LIFTED"):
                continue
            if s[kind][gid] == state_mod.TO_CONFIRM:
                add(HUMAN, f"confirm {gid} (it rests on a doubtful entry)")
            elif not g["requests"]:
                add(g["by"], f"{verb} {gid}")
            else:
                for a in g["missing"]:
                    add(a, f"ACK {g['requests'][-1]} (to {verb.lower()} {gid})")
    for hid, h in d["handoffs"].items():
        status = s["handoffs"][hid]
        if status == state_mod.TO_CONFIRM:
            add(HUMAN, f"confirm {hid} (it rests on a doubtful entry)")
        elif status != "RECEIVED":
            add(h["to"], f"RECEIPT {hid}" + (" (the last one does not match)" if status == "MISMATCH" else ""))
    for did, x in d["disputes"].items():
        status = s["disputes"][did]
        if status == "OPEN":
            add(d["proposals"][x["proposal"]]["by"], f"answer {did}")
        elif status == "ANSWERED":
            add(x["by"], f"ACK {x['proposal']} or keep {did} open")
    for cid in d["conflicts"]:
        status = s["conflicts"][cid]
        if status == "OPEN":
            add(THIRD, f"ARBITRATE {cid}")
        elif status == "ESCALATED":
            add(HUMAN, f"decide {cid} (no rule covers it)")
    return out


def summary(st, title: str = "", head: str = "") -> dict:
    counts = {kind: {} for kind in state_mod.KINDS}
    for kind in state_mod.KINDS:
        for status in st.status[kind].values():
            counts[kind][status] = counts[kind].get(status, 0) + 1
    out = {"as_of": st.as_of, "title": title, "release_gate": st.release_gate, "release_reasons": st.release_reasons,
           "counts": counts, "state": st.status, "pending_by_agent": pending(st),
           "open_disputes": sorted(i for i, s in st.status["disputes"].items() if s == "OPEN"),
           "responses_by_nature": st.details["responses"]["by_nature"],
           "lint": {"errors": len(st.errors), "warnings": len(st.findings) - len(st.errors)},
           "degraded": st.degraded}
    if head:
        out["head"] = head
    return out


def render(sm: dict) -> str:
    a = sm["as_of"]
    lines = [f"status as of commit {a.get('commit_index')} ({a.get('committed_utc')})"
             + (f", head {sm['head'][:12]}" if sm.get("head") else "") + (f" - {sm['title']}" if sm["title"] else "")]
    lines.append(f"release gate: {sm['release_gate']}" + (" - " + "; ".join(sm["release_reasons"]) if sm["release_reasons"] else ""))
    for kind in state_mod.KINDS:
        if sm["counts"][kind]:
            lines.append(f"{kind}: " + ", ".join(f"{n} {s}" for s, n in sorted(sm["counts"][kind].items())))
    n = sm["responses_by_nature"]
    lines.append(f"responses: {n['note']} note(s), {n['dissent']} dissent(s), {n['none']} plain; "
                 f"open disputes: {len(sm['open_disputes'])}" + (f" ({', '.join(sm['open_disputes'])})" if sm["open_disputes"] else ""))
    if sm["pending_by_agent"]:
        lines.append("waiting for:")
        for agent, what in sm["pending_by_agent"].items():
            lines.append(f"  {agent}: " + "; ".join(what))
    else:
        lines.append("waiting for: nobody")
    if sm["degraded"]:
        lines.append("state DEGRADED: " + "; ".join(sm["degraded"][:3]))
    lint = sm["lint"]
    lines.append(f"lint: {'FAILED' if lint['errors'] else 'OK'} - {lint['errors']} error(s), {lint['warnings']} warning(s)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coord.status", description="State of a coordination, derived from its git log.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", help="directory with the rule files (default: rules/)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-sha", action="store_true", help="name the head commit by index only")
    a = ap.parse_args(argv)
    try:
        log = gitlog.read(a.repo)
        st = state_mod.derive(log, load(a.rules))
    except (gitlog.LogError, gitlog.fixture.GitError, OSError, ValueError) as exc:
        sys.stdout.buffer.write(f"status: FAILED - the repository could not be read: {exc}\n".encode("utf-8"))
        return 2
    header = parse_doc(log.head_files.get(gitlog.DOC, b"")).header.split("\n")[0]
    title = header[len("# COORD - "):] if header.startswith("# COORD - ") else ""
    sm = summary(st, title, "" if a.no_sha else st.head_sha)
    text = json.dumps(sm, indent=2, sort_keys=True, ensure_ascii=False) if a.json else render(sm)
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
