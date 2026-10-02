"""What each tolerated spelling is worth, measured on the stress-diagnosis corpus.

    python eval/ablation.py --out build/eval/ablation.json

Scores the stress-diag corpus (seed 20261002, stress profile) with every tolerated spelling of
`coord/parse.py` switched on, with none, and with each one switched off in turn. A tolerance that changes
nothing on this corpus has no measured justification and should be removed.

This is a diagnosis on a set the author has seen: it justifies the list, it is not evidence of quality.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coord import fixture, parse                     # noqa: E402
from corpus import generate                          # noqa: E402
from eval import score                               # noqa: E402


def measure(corpus: Path, work: Path, index: dict) -> dict:
    res = score.score_corpus(corpus, work, index)
    o, v = res["objects"]["all"], res["violations"]["all"]
    return {"objects_exact": o["exact"], "objects": o["gold"], "objects_exact_rate": o["exact_rate"],
            "stories_exact": res["stories_exact"], "tool_to_confirm": o["tool_to_confirm"],
            "violations_precision": v["precision"], "violations_recall": v["recall"],
            "structural_findings": res["structural_findings"],
            "wrong_assertions": res["wrong_assertions"], "never_events": res["never_events"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Leave-one-out measurement of the tolerated spellings.")
    ap.add_argument("--work")
    ap.add_argument("--out")
    ap.add_argument("--n", type=int, default=generate.DEFAULT_N)
    a = ap.parse_args(argv)
    work = Path(a.work) if a.work else ROOT / "build" / "eval" / "ablation"
    fixture.rmtree(work)
    seed = generate.AUTHOR_SEEDS["stress-diag"]
    index = generate.generate(seed, work / "corpus", "stress", a.n)
    everything = set(parse.TOLERATED)
    runs = {}
    try:
        for label, active in [("all", everything), ("none", set())] + [(f"without {k}", everything - {k})
                                                                         for k in sorted(everything)]:
            parse.ACTIVE.clear()
            parse.ACTIVE.update(active)
            runs[label] = measure(work / "corpus", work / "repos", index)
            r = runs[label]
            print(f"{label:28s} objects exact {r['objects_exact']}/{r['objects']} stories exact {r['stories_exact']} "
                  f"wrong assertions {r['wrong_assertions']} never-events {r['never_events']}")
    finally:
        parse.ACTIVE.clear()
        parse.ACTIVE.update(everything)
    out = {"suite": "stress-diag", "seed": seed, "profile": "stress", "stories": a.n,
           "corpus_sha256": generate.digest(index), "runs": runs}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
