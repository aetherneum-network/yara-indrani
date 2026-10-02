"""S03 - the same question asked twice with a commit in between: the answer and its `as_of` both move."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()


def ask(label: str) -> dict:
    code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
    s.eq(f"{label} question: status exits 0", code, 0)
    s.write(f"status_{label}.json", out)
    return json.loads(out)


first = ask("first")
_, st = s.state(repo)
s.against_gold(st, s.expected("gold_first.json"), "first question")
s.eq("first answer: as_of", first["as_of"], want["first"]["as_of"])
s.subset("first answer: the proposal is not aligned yet", first["state"]["proposals"], want["first"]["proposals"])
s.eq("first answer: who is waited for", first["pending_by_agent"], want["first"]["waiting_for"])

s.append(repo, "later.fi")                       # one more commit lands in the shared log

second = ask("second")
_, st = s.state(repo)
s.against_gold(st, s.expected("gold.json"), "second question")
s.eq("second answer: as_of", second["as_of"], want["second"]["as_of"])
s.subset("second answer: the proposal is aligned", second["state"]["proposals"], want["second"]["proposals"])
s.eq("second answer: who is waited for", second["pending_by_agent"], want["second"]["waiting_for"])
s.true("the as_of moved with the log", first["as_of"] != second["as_of"])
s.true("the first answer was not reused", first["state"] != second["state"])
raise SystemExit(s.finish())
