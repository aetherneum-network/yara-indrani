"""Arbitration of two claims on the same resource, by ordered rules.

`rules/arbitration.json` is read top to bottom; the first rule whose condition holds gives the outcome and
its id is cited. If no rule holds, the outcome is ESCALATE_TO_HUMAN: the tool never invents a winner.

The register (`arbitrations/ARB-*.json`) is append-only: a record is never rewritten. When a rule change
gives a different outcome for a conflict already recorded, a new record is added that names the one it
supersedes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from coord.parse import ESCALATE
from coord.rules import RuleError

SCHEMA = "coord/arbitration/1"


def _pair(arg: dict) -> tuple[str, str]:
    (key, value), = arg.items()
    return key, value


def _holds(when: dict, p: dict, q: dict) -> bool:
    for cond, arg in when.items():
        if cond == "exactly_one":
            k, v = _pair(arg)
            ok = (p.get(k) == v) != (q.get(k) == v)
        elif cond == "neither":
            k, v = _pair(arg)
            ok = p.get(k) != v and q.get(k) != v
        elif cond == "both":
            k, v = _pair(arg)
            ok = p.get(k) == v and q.get(k) == v
        elif cond == "both_have":
            ok = bool(p.get(arg)) and bool(q.get(arg))
        elif cond == "differ":
            ok = p.get(arg) != q.get(arg)
        elif cond == "same":
            ok = p.get(arg) == q.get(arg)
        else:
            raise RuleError(f"unknown arbitration condition '{cond}'")
        if not ok:
            return False
    return True


def _winner(then: dict, p: dict, q: dict) -> str:
    w = then.get("winner")
    if w == "first":
        return p["id"]
    if isinstance(w, dict) and "with" in w:
        k, v = _pair(w["with"])
        hit = [c for c in (p, q) if c.get(k) == v]
        if len(hit) == 1:
            return hit[0]["id"]
    elif isinstance(w, dict) and "lowest" in w:
        a, b = p.get(w["lowest"]), q.get(w["lowest"])
        if a and b and a != b:
            return (p if a < b else q)["id"]
    raise RuleError("an arbitration rule matched but does not name one winner")


def decide(rule_file: dict, p: dict, q: dict) -> tuple[str, str]:
    """(rule id, winner id) for two claims, `p` being the earlier one in the log; ('none', ESCALATE_TO_HUMAN)
    when no rule covers the case."""
    default = rule_file.get("default_class", "routine")
    p, q = dict(p, **{"class": p.get("class") or default}), dict(q, **{"class": q.get("class") or default})
    for rule in rule_file["rules"]:
        if _holds(rule.get("when", {}), p, q):
            return rule["id"], _winner(rule["then"], p, q)
    return "none", ESCALATE


# -- the append-only register -------------------------------------------------------------------------------

def records(state) -> list[dict]:
    """One record per conflict of a derived state, without an id yet."""
    out = []
    for cid, c in state.details["conflicts"].items():
        out.append({"schema": SCHEMA, "conflict": cid, "resource": c["resource"], "claims": c["claims"],
                    "rule": c["expected"]["rule"], "outcome": c["expected"]["outcome"],
                    "rules_version": state.rules_version["arbitration"], "rules_sha256": state.rules_sha256["arbitration"],
                    "as_of": state.as_of, "recorded_in_log": c["recorded"], "dissents": c["dissents"]})
    return out


def read_register(directory: str | Path) -> list[dict]:
    d = Path(directory)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("ARB-*.json"))] if d.is_dir() else []


def append(new: list[dict], directory: str | Path) -> list[dict]:
    """Add to the register the records that say something new. Returns the records written."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    existing = read_register(d)
    latest = {r["conflict"]: r for r in existing}
    n = len(existing)
    written = []
    for rec in new:
        old = latest.get(rec["conflict"])
        if old is not None and (old["rule"], old["outcome"]) == (rec["rule"], rec["outcome"]):
            continue
        n += 1
        rec = dict(rec, id=f"ARB-{n:04d}", supersedes=old["id"] if old else None)
        with open(d / f"{rec['id']}.json", "x", encoding="utf-8", newline="\n") as fh:     # 'x': never overwrite
            fh.write(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        latest[rec["conflict"]] = rec
        written.append(rec)
    return written


def main(argv: list[str] | None = None) -> int:
    from coord import gitlog, rules as rules_mod, state as state_mod

    ap = argparse.ArgumentParser(prog="coord.arbitrate", description="Arbitrate resource conflicts by ordered rules.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", help="directory with the rule files (default: rules/)")
    ap.add_argument("--register", help="append the outcomes to this register directory")
    a = ap.parse_args(argv)
    st = state_mod.derive(gitlog.read(a.repo), rules_mod.load(a.rules))
    recs = records(st)
    lines = [f"{r['conflict']} [{r['resource']}]: rule {r['rule']} -> {r['outcome']}" for r in recs]
    if a.register:
        for r in append(recs, a.register):
            tail = f" (supersedes {r['supersedes']})" if r["supersedes"] else ""
            lines.append(f"recorded {r['id']}: {r['conflict']} -> {r['outcome']}{tail}")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
