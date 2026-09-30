"""Score the tooling against the gold of a generated corpus.

    python eval/score.py --suite dev                      # seed 20260930, standard profile (the author's dev set)
    python eval/score.py --suite stress-diag              # seed 20261002, stress profile (declared diagnosis)
    python eval/score.py --suite blind --seed N --profile standard --runner "who runs it"

For each story the corpus holds a git history (as a fast-import stream) and a gold computed from the
events by `corpus/reference_reducer.py`, which shares no code with the tooling. The score compares, per
story: the status of every object, the release gate, the violations (class, commit index, target), the
dependency edges and the arbitration outcomes.

What it measures is internal consistency on synthetic stories: that two independent implementations of
PROTOCOL.md agree. It says nothing about real teams.

The blind suite refuses the two seeds the author used, refuses to run on code that differs from the
frozen one (`eval/FREEZE.sha256`), and refuses to overwrite a result: it is meant to be run once, by a
different hand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coord import fixture, parse, state as state_mod                    # noqa: E402
from coord.rules import load as load_rules                        # noqa: E402
from corpus import generate                                       # noqa: E402

FROZEN_PATHS = ("coord", "corpus", "rules", "schemas", "templates", "eval/score.py", "eval/blind_hand.py", "PROTOCOL.md")
NEVER = {"proposals": ("ALIGNED", "DECIDED"), "blocks": ("REMOVED",), "freezes": ("LIFTED",)}


def rate(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def frozen_files() -> dict[str, str]:
    """SHA-256 of every file the blind run depends on (line endings normalised)."""
    out = {}
    for rel in FROZEN_PATHS:
        p = ROOT / rel
        files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file())
        for f in files:
            r = f.relative_to(ROOT).as_posix()
            if "__pycache__" in r or r.startswith("corpus/out/"):
                continue
            out[r] = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return out


def check_frozen() -> list[str]:
    """Differences between the code on disk and eval/FREEZE.sha256 ([] = identical)."""
    listing = ROOT / "eval" / "FREEZE.sha256"
    if not listing.is_file():
        return ["eval/FREEZE.sha256 is missing: the code was never frozen"]
    want = dict(reversed(line.split("  ", 1)) for line in listing.read_text(encoding="utf-8").splitlines() if line.strip())
    have = frozen_files()
    return [f"{path}: {'changed' if path in want and path in have else 'missing' if path in want else 'not in the freeze'}"
            for path in sorted(set(want) | set(have)) if want.get(path) != have.get(path)]


def score_story(gold: dict, st, doc_state) -> dict:
    tool = st.as_dict()
    r = {"objects": {}, "wrong_assertions": [], "never_events": [], "mismatches": []}
    for kind in state_mod.KINDS:
        g, t = gold["state"][kind], tool["state"][kind]
        exact = sum(1 for oid in g if t.get(oid) == g[oid])
        r["objects"][kind] = {"gold": len(g), "exact": exact, "extra": len(set(t) - set(g)),
                              "gold_to_confirm": sum(1 for s in g.values() if s == state_mod.TO_CONFIRM),
                              "tool_to_confirm": sum(1 for s in t.values() if s == state_mod.TO_CONFIRM),
                              "tool_only_to_confirm": sum(1 for oid, s in t.items() if s == state_mod.TO_CONFIRM
                                                          and g.get(oid) not in (None, state_mod.TO_CONFIRM))}
        for oid in sorted(set(g) | set(t)):
            if g.get(oid) == t.get(oid):
                continue
            r["mismatches"].append(f"{kind} {oid}: tool {t.get(oid)}, gold {g.get(oid)}")
            if t.get(oid) in state_mod.ASSERTING[kind]:
                r["wrong_assertions"].append(f"{kind} {oid}: tool {t.get(oid)}, gold {g.get(oid)}")
                if t.get(oid) in NEVER.get(kind, ()):
                    r["never_events"].append(f"{kind} {oid}: tool {t.get(oid)}, gold {g.get(oid)}")
    r["gate_exact"] = tool["release_gate"] == gold["release_gate"]
    if tool["release_gate"] == "OPEN" and gold["release_gate"] == "BLOCKED":
        r["never_events"].append("release gate: tool OPEN, gold BLOCKED")
    key = lambda v: (v["class"], v["commit_index"], v["target"])
    gv, tv = {key(v) for v in gold["violations"]}, {key(v) for v in tool["violations"]}
    r["violations"] = {"tp": sorted(gv & tv), "fp": sorted(tv - gv), "fn": sorted(gv - tv)}
    r["structural"] = [f.cls for f in st.findings if f.severity == "error" and not f.cls.startswith("V")]
    edge = lambda e: (e["block"], e["on"], e["refs"], e["active"])
    r["edges_exact"] = sorted(map(edge, tool["edges"])) == sorted(map(edge, gold["edges"]))
    arb = lambda a: (a["conflict"], a["rule"], a["outcome"])
    r["arbitrations_exact"] = sorted(map(arb, tool["arbitrations"])) == sorted(map(arb, gold["arbitrations"]))
    r["doc_agrees"] = doc_state.status == st.status and doc_state.release_gate == st.release_gate
    r["exact"] = (not r["mismatches"] and r["gate_exact"] and not r["violations"]["fp"] and not r["violations"]["fn"]
                  and r["edges_exact"] and r["arbitrations_exact"])
    return r


def score_corpus(corpus: Path, work: Path, index: dict) -> dict:
    rules = load_rules()
    kinds = {k: {"gold": 0, "exact": 0, "extra": 0, "gold_to_confirm": 0, "tool_to_confirm": 0, "tool_only_to_confirm": 0}
             for k in state_mod.KINDS}
    classes = {f"V{i:02d}": {"gold": 0, "tp": 0, "fp": 0, "fn": 0} for i in range(1, 12)}
    total = {"stories": 0, "stories_exact": 0, "gate_exact": 0, "edges_exact": 0, "arbitrations_exact": 0,
             "wrong_assertions": 0, "never_events": 0}
    doc = {"clean_stories": 0, "clean_agree": 0, "planted_stories": 0, "planted_disagree": 0}
    structural: dict[str, int] = {}
    notes: list[str] = []
    for row in index["stories"]:
        sid = row["id"]
        gold = json.loads((corpus / sid / "gold.json").read_text(encoding="utf-8"))
        repo = fixture.build_repo((corpus / sid / "stream.fi").read_bytes(), work / f"{sid}.git")
        log = state_mod.gitlog.read(repo)
        st = state_mod.derive(log, rules)
        r = score_story(gold, st, state_mod.from_document(log.head_files.get("COORD.md", b""), rules))
        fixture.rmtree(repo)
        total["stories"] += 1
        for k in ("gate_exact", "edges_exact", "arbitrations_exact"):
            total[k] += r[k]
        total["stories_exact"] += r["exact"]
        total["wrong_assertions"] += len(r["wrong_assertions"])
        total["never_events"] += len(r["never_events"])
        for kind in state_mod.KINDS:
            for k, v in r["objects"][kind].items():
                kinds[kind][k] += v
        for bucket in ("tp", "fp", "fn"):
            for cls, _, _ in r["violations"][bucket]:
                classes[cls][bucket] += 1
                if bucket != "fp":
                    classes[cls]["gold"] += 1
        for cls in r["structural"]:
            structural[cls] = structural.get(cls, 0) + 1
        if row["clean"]:
            doc["clean_stories"] += 1
            doc["clean_agree"] += r["doc_agrees"]
        else:
            doc["planted_stories"] += 1
            doc["planted_disagree"] += not r["doc_agrees"]
        for line in r["never_events"] + r["mismatches"][:3] + [f"violation not reported: {v}" for v in r["violations"]["fn"][:3]] \
                + [f"violation reported but not in the gold: {v}" for v in r["violations"]["fp"][:3]]:
            if len(notes) < 40:
                notes.append(f"{sid}: {line}")
    everything = {k: sum(kinds[kind][k] for kind in kinds) for k in next(iter(kinds.values()))}
    for d in list(kinds.values()) + [everything]:
        d["exact_rate"] = rate(d["exact"], d["gold"])
    allv = {k: sum(c[k] for c in classes.values()) for k in ("gold", "tp", "fp", "fn")}
    for c in list(classes.values()) + [allv]:
        c["precision"], c["recall"] = rate(c["tp"], c["tp"] + c["fp"]), rate(c["tp"], c["tp"] + c["fn"])
    return {"seed": index["seed"], "profile": index["profile"], "stories": total["stories"],
            "commits": sum(r["commits"] for r in index["stories"]), "corpus_sha256": generate.digest(index),
            "stories_planting_class": index["stories_planting_class"],
            "objects": dict(kinds, all=everything), "stories_exact": total["stories_exact"],
            "wrong_assertions": total["wrong_assertions"], "never_events": total["never_events"],
            "release_gate_exact": total["gate_exact"], "edges_exact_stories": total["edges_exact"],
            "arbitrations_exact_stories": total["arbitrations_exact"],
            "violations": dict(classes, all=allv), "structural_findings": dict(sorted(structural.items())),
            "document_vs_log": doc, "first_differences": notes,
            "rules_sha256": rules.sha256, "tolerated_spellings": sorted(parse.TOLERATED)}


def summary(res: dict) -> str:
    o, v = res["objects"]["all"], res["violations"]["all"]
    return (f"{res['suite']} seed={res['seed']} profile={res['profile']} stories={res['stories']} commits={res['commits']}: "
            f"objects exact {o['exact']}/{o['gold']} ({o['exact_rate']}), stories exact {res['stories_exact']}/{res['stories']}, "
            f"violations precision {v['precision']} recall {v['recall']} (tp {v['tp']}, fp {v['fp']}, fn {v['fn']}), "
            f"TO_CONFIRM tool {o['tool_to_confirm']} / gold {o['gold_to_confirm']}, "
            f"wrong assertions {res['wrong_assertions']}, never-events {res['never_events']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score the tooling against a generated corpus.")
    ap.add_argument("--suite", required=True, choices=("dev", "stress-diag", "blind"))
    ap.add_argument("--seed", type=int, help="blind suite only")
    ap.add_argument("--profile", choices=generate.PROFILES, help="blind suite only (default: standard)")
    ap.add_argument("--runner", help="blind suite only: who runs it")
    ap.add_argument("--n", type=int, default=generate.DEFAULT_N)
    ap.add_argument("--work", help="work directory (default: build/eval/<suite>)")
    ap.add_argument("--out", help="write the result as JSON to this file")
    a = ap.parse_args(argv)

    extra: dict = {}
    if a.suite == "blind":
        if a.seed is None or not a.runner:
            print("FAILED: the blind suite needs --seed and --runner")
            return 2
        if a.seed in generate.AUTHOR_SEEDS.values():
            print(f"FAILED: seed {a.seed} was used by the author of the pack; a blind run needs a seed the author never saw")
            return 2
        changed = check_frozen()
        if changed:
            print("FAILED: the code differs from the frozen one: " + "; ".join(changed[:8]))
            return 2
        seed, profile = a.seed, a.profile or "standard"
        out = Path(a.out) if a.out else ROOT / "eval" / "blind" / f"blind-{seed}-{profile}.json"
        if out.exists():
            print(f"FAILED: {out.name} already exists; a blind seed is run once")
            return 2
        extra = {"runner": a.runner, "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "git": ".".join(map(str, fixture.git_version())), "python": sys.version.split()[0]}
    else:
        if a.seed is not None or a.profile:
            print("FAILED: --seed and --profile belong to the blind suite; dev and stress-diag have fixed ones")
            return 2
        seed = generate.AUTHOR_SEEDS[a.suite]
        profile = "stress" if a.suite == "stress-diag" else "standard"
        out = Path(a.out) if a.out else None
    work = Path(a.work) if a.work else ROOT / "build" / "eval" / a.suite
    fixture.rmtree(work)
    index = generate.generate(seed, work / "corpus", profile, a.n)
    res = {"suite": a.suite, **score_corpus(work / "corpus", work / "repos", index), **extra}
    text = json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x" if a.suite == "blind" else "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(summary(res))
    for line in res["first_differences"][:12]:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
