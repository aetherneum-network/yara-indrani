"""Dependency graph: which proposal waits for which, who blocks whom, and cycles.

An edge comes from a `BLOCK` with an `on` field: the proposal in `on` must be settled before the proposal
in `refs` can be decided (blocking -> blocked). Only active blocks count.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque


def closing_cycle(active: list[tuple[str, str, str]], blocked: str, waits_for: str) -> list[str]:
    """`active` = (block id, on, refs) of the active blocks, in log order. A new block makes `blocked` wait for
    `waits_for`. If that closes a cycle, the ids of the blocks already in it (shortest chain); else []."""
    queue, seen = deque([(blocked, [])]), {blocked}
    while queue:
        node, path = queue.popleft()
        for bid, on, refs in active:
            if on != node:
                continue
            if refs == waits_for:
                return path + [bid]
            if refs not in seen:
                seen.add(refs)
                queue.append((refs, path + [bid]))
    return []


def head_cycles(edges: list[dict]) -> list[list[str]]:
    """Cycles among the active edges at head, each as the list of its block ids in log order."""
    active = [(e["block"], e["on"], e["refs"]) for e in edges if e["active"]]
    order = {bid: i for i, (bid, _, _) in enumerate(active)}
    found: list[list[str]] = []
    for i, (bid, on, refs) in enumerate(active):
        rest = active[:i] + active[i + 1:]
        chain = closing_cycle(rest, refs, on)
        if chain:
            cycle = sorted(chain + [bid], key=order.__getitem__)
            if cycle not in found:
                found.append(cycle)
    return found


def graph(state) -> dict:
    """The dependency view of a derived state (see coord/state.py)."""
    blocks = state.details["blocks"]
    proposals = state.details["proposals"]
    edges = [dict(e) for e in state.edges]
    who = []
    for bid, b in blocks.items():
        if state.status["blocks"][bid] == "REMOVED":
            continue
        row = {"agent": b["by"], "blocks": proposals[b["refs"]]["by"], "proposal": b["refs"], "block": bid,
               "missing_consents": b["missing"]}
        if b.get("on"):
            row["waiting_for"] = {"proposal": b["on"], "owner": proposals[b["on"]]["by"]}
        who.append(row)
    return {"nodes": sorted(proposals), "edges": edges, "cycles": head_cycles(edges), "who_blocks_whom": who}


def render(g: dict) -> str:
    lines = [f"dependencies: {len(g['edges'])} edge(s), {sum(1 for e in g['edges'] if e['active'])} active, "
             f"{len(g['cycles'])} cycle(s)"]
    for e in g["edges"]:
        lines.append(f"  {e['on']} -> {e['refs']}  (block {e['block']}, {'active' if e['active'] else 'removed'})")
    for c in g["cycles"]:
        lines.append(f"CYCLE: {' + '.join(c)}")
    for w in g["who_blocks_whom"]:
        tail = f", waiting for {w['waiting_for']['proposal']} of {w['waiting_for']['owner']}" if "waiting_for" in w else ""
        lines.append(f"  {w['agent']} blocks {w['blocks']} on {w['proposal']} (block {w['block']}{tail})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from coord import gitlog, state as state_mod

    ap = argparse.ArgumentParser(prog="coord.deps", description="Dependency graph of a coordination repository.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    g = graph(state_mod.derive(gitlog.read(a.repo)))
    text = json.dumps(g, indent=2, sort_keys=True, ensure_ascii=False) + "\n" if a.json or a.out else render(g) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 3 if g["cycles"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
