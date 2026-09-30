"""Write the `input/` and `expected/` folders of the ten scenarios from `scenarios/stories.py`.

    python scenarios/make_inputs.py            # rewrite them
    python scenarios/make_inputs.py --check    # verify that the committed ones are what the stories give

`input/` holds the git history of the story as fast-import streams (and, for S09, the second rule set).
`expected/declared.json` is what the author of the story wrote by hand; `expected/gold*.json` is what the
reference reducer computes from the events. A scenario check compares the tooling with both.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus import render                                   # noqa: E402
from corpus.reference_reducer import reduce_events          # noqa: E402
from scenarios.stories import STORIES                       # noqa: E402

TIE_RULE = {"id": "R-TIE-FIRST", "when": {"neither": {"class": "safety"}, "both_have": "due", "same": "due"},
            "then": {"winner": "first"}}


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def rules_v2() -> dict[str, bytes]:
    """The rule files with one more arbitration rule: a tie on the due date goes to the first claim."""
    out = {}
    for path in sorted((ROOT / "rules").glob("*.json")):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        if path.name == "arbitration.json":
            obj = json.loads(data.decode("utf-8"))
            obj["version"] = 2
            at = [r["id"] for r in obj["rules"]].index("R-DUE") + 1
            obj["rules"].insert(at, TIE_RULE)
            data = dumps(obj)
        out[f"input/rules_v2/{path.name}"] = data
    return out


def files_of(name: str) -> dict[str, bytes]:
    """Relative path -> content of every generated file of a scenario."""
    events, declared = STORIES[name]()
    out = {"expected/declared.json": dumps(declared)}
    if name.startswith("S04"):
        for label, ev in events.items():
            out[f"input/{label}.fi"] = render.stream(ev)
            out[f"input/{label}.events.json"] = dumps(ev)
            out[f"expected/gold_{label}.json"] = dumps(reduce_events(ev))
        return out
    out["input/events.json"] = dumps(events)
    out["expected/gold.json"] = dumps(reduce_events(events))
    if name.startswith(("S03", "S06")):
        k = declared["split_after"]
        out["input/stream.fi"] = render.stream(events[:k])
        out["input/later.fi"] = render.stream(events, start=k + 1)
        out["expected/gold_first.json"] = dumps(reduce_events(events[:k]))
    elif name.startswith("S10"):
        d = declared
        main = "refs/heads/main^0"
        out["input/stream.fi"] = render.stream(events[:d["base"]])
        out["input/bruno.fi"] = render.stream(events, select={d["bruno"]}, ref="refs/heads/submit-bruno",
                                              external={d["base"]: main})
        out["input/carla.fi"] = render.stream(events, select={d["carla"]}, ref="refs/heads/submit-carla",
                                              external={d["base"]: main})
        out["input/carla-merge.fi"] = render.stream(events, select={d["merge"]}, ref="refs/heads/submit-carla",
                                                    external={d["carla"]: "refs/heads/submit-carla^0", d["bruno"]: main})
    else:
        out["input/stream.fi"] = render.stream(events)
    if name.startswith("S09"):
        out.update(rules_v2())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write or verify the scenario inputs.")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    stale = []
    for name in STORIES:
        for rel, data in files_of(name).items():
            path = HERE / name / rel
            if a.check:
                if not path.is_file() or path.read_bytes().replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                    stale.append(f"{name}/{rel}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
    if a.check:
        print(f"scenario inputs: {'FAILED - stale: ' + ', '.join(stale) if stale else 'OK - they are what the stories give'}")
        return 1 if stale else 0
    print(f"wrote the inputs of {len(STORIES)} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
