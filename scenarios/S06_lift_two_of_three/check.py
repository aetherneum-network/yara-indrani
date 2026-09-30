"""S06 - a freeze with two consents out of three stays frozen; the third consent lifts it."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
(fid, _), = want["two_of_three"]["freezes"].items()

_, st = s.state(repo)
w = want["two_of_three"]
s.against_gold(st, s.expected("gold_first.json"), "two of three")
s.eq("two of three: the freeze is still FROZEN", st.status["freezes"], w["freezes"])
s.eq("two of three: the release gate is BLOCKED", st.release_gate, w["release_gate"])
s.eq("two of three: the missing consent is named", st.details["freezes"][fid]["missing"], w["missing"])
code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
s.eq("two of three: status says who is waited for", json.loads(out)["pending_by_agent"], w["waiting_for"])
s.true("two of three: the gate gives its reason", bool(json.loads(out)["release_reasons"]), out)
s.write("status_two_of_three.json", out)

s.append(repo, "later.fi")                       # the third consent is committed by its own author

_, st = s.state(repo)
w = want["three_of_three"]
s.against_gold(st, s.expected("gold.json"), "three of three")
s.eq("three of three: the freeze is LIFTED", st.status["freezes"], w["freezes"])
s.eq("three of three: the release gate is OPEN", st.release_gate, w["release_gate"])
s.eq("three of three: nothing is missing", st.details["freezes"][fid]["missing"], w["missing"])
s.eq("no violation in either state", st.violations, [])
code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
s.write("status_three_of_three.json", out)
raise SystemExit(s.finish())
