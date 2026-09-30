"""S02 - a build number is received with two digits transposed: the hand-off is not closed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
log, st = s.state(repo)
(hid, status), = want["handoffs"].items()

s.against_gold(st, s.expected("gold.json"))
s.eq("the hand-off is a MISMATCH, not RECEIVED", st.status["handoffs"], {hid: status})
s.eq("the release gate is BLOCKED", st.release_gate, want["release_gate"])
s.eq("one violation, at the commit of the receipt", st.violations, want["violations"])
s.eq("the difference is the transposed build number, anchor by anchor", st.details["handoffs"][hid]["diff"], want["diff"])
s.eq("both files are cited", st.details["handoffs"][hid]["files"], want["cites"])
s.subset("the decision made before the hand-off stands", st.status["proposals"], want["proposals"])

code, out = s.cli("coord.sentinel", "--repo", repo)
s.eq("the sentinel exits 3", code, 3)
for needle in want["cites"] + [want["diff"][0]["handoff"], want["diff"][0]["receipt"]]:
    s.true(f"the sentinel report names {needle}", needle in out, out)
s.write("sentinel.txt", out)

code, out = s.cli("coord.lint", "--repo", repo, "--no-sha")
s.eq("lint exits 3", code, 3)
s.true("lint says FAILED in its first line", out.startswith("lint: FAILED"), out)
s.write("lint.txt", out)

code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
answer = json.loads(out)
s.true("status waits for a matching receipt from the receiver",
       any(w.startswith(f"RECEIPT {hid}") for w in answer["pending_by_agent"].get("oscar", [])), out)
s.write("state.json", st.to_json())
raise SystemExit(s.finish())
