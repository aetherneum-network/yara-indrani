"""Blind run, second half: cycles written by hand by someone who is not the author of the pack.

    python eval/blind_hand.py --repo <repository> --declared <declared.json> --runner "who wrote the cycles"

The runner receives only PROTOCOL.md and templates/COORD.md, writes coordination cycles in a git
repository of their own (one commit per entry, each commit made with the email of its `by` agent), and
writes down beforehand the state they intend. This command derives the state from the log with the frozen
code and compares, object by object. It reports the differences as they are; it fixes nothing.

`declared.json` holds any of: "proposals", "blocks", "freezes", "handoffs", "disputes", "conflicts"
(each a map id -> status), "release_gate", "violations" (a list of classes, e.g. ["V05"]; [] = none).

Like the seeded blind suite, it refuses to run on code that differs from eval/FREEZE.sha256 and refuses
to overwrite a result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coord import fixture, gitlog, state as state_mod        # noqa: E402
from coord.rules import load as load_rules                   # noqa: E402
from eval import score                                       # noqa: E402


def compare(declared: dict, st) -> dict:
    rows, exact = [], 0
    for kind in state_mod.KINDS:
        for oid, want in sorted(declared.get(kind, {}).items()):
            got = st.status[kind].get(oid)
            rows.append({"kind": kind, "id": oid, "declared": want, "derived": got, "exact": got == want})
            exact += got == want
    out = {"objects_declared": len(rows), "objects_exact": exact, "objects": rows,
           "undeclared_objects": sorted(f"{k} {o}" for k in state_mod.KINDS for o in st.status[k] if o not in declared.get(k, {}))}
    if "release_gate" in declared:
        out["release_gate"] = {"declared": declared["release_gate"], "derived": st.release_gate,
                               "exact": declared["release_gate"] == st.release_gate}
    if "violations" in declared:
        got = sorted(v["class"] for v in st.violations)
        out["violations"] = {"declared": sorted(declared["violations"]), "derived": got, "exact": sorted(declared["violations"]) == got}
    out["structural_findings"] = sorted(f.cls for f in st.errors if not f.cls.startswith("V"))
    out["lint"] = [f.as_dict() for f in st.findings]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare hand-written cycles with the state their author declared.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--declared", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("--out", help="result file (default: eval/blind/hand-<runner>.json)")
    ap.add_argument("--ref", default="main", help="branch that holds the shared log (default: main)")
    a = ap.parse_args(argv)
    changed = score.check_frozen()
    if changed:
        print("FAILED: the code differs from the frozen one: " + "; ".join(changed[:8]))
        return 2
    slug = re.sub(r"[^a-z0-9]+", "-", a.runner.lower()).strip("-") or "runner"
    out = Path(a.out) if a.out else ROOT / "eval" / "blind" / f"hand-{slug}.json"
    if out.exists():
        print(f"FAILED: {out.name} already exists; a blind run is done once")
        return 2
    declared = json.loads(Path(a.declared).read_text(encoding="utf-8"))
    try:
        st = state_mod.derive(gitlog.read(a.repo, a.ref), load_rules())
    except (gitlog.LogError, fixture.GitError, OSError, ValueError) as exc:
        print(f"FAILED: the repository could not be read: {exc}")
        return 2
    res = {"suite": "blind-hand", "runner": a.runner, "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "commits": st.commits, "as_of": st.as_of, "git": ".".join(map(str, fixture.git_version())),
           "python": sys.version.split()[0], **compare(declared, st)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"blind-hand runner={a.runner} commits={st.commits}: objects exact {res['objects_exact']}/{res['objects_declared']}"
          + (f", release gate {'exact' if res['release_gate']['exact'] else 'DIFFERENT'}" if "release_gate" in res else "")
          + (f", violations {'exact' if res['violations']['exact'] else 'DIFFERENT'}" if "violations" in res else "")
          + f", structural findings {len(res['structural_findings'])}")
    for row in res["objects"]:
        if not row["exact"]:
            print(f"  {row['kind']} {row['id']}: declared {row['declared']}, derived {row['derived']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
