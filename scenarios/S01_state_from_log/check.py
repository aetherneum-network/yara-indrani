"""S01 - the state of three clean cycles is read from the git log, by three independent routes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402
from coord import state as state_mod              # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
log, st = s.state(repo)

s.against_gold(st, s.expected("gold.json"))
for kind in ("proposals", "disputes", "handoffs"):
    s.subset(f"{kind} = what the author of the story declared", st.status[kind], want[kind])
s.eq("release gate = declared", st.release_gate, want["release_gate"])
s.eq("no violation", st.violations, want["violations"])
s.eq("nothing rests on a doubtful entry", st.doubtful, {})

doc = state_mod.from_document(log.head_files["COORD.md"])
s.eq("on a clean story the document alone gives the same statuses", doc.status, st.status)

code, out = s.cli("coord.lint", "--repo", repo, "--no-sha")
s.eq("lint exits 0", code, 0)
s.true("lint says OK in its first line", out.startswith("lint: OK"), out)
s.write("lint.txt", out)

code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
answer = json.loads(out)
s.eq("status exits 0", code, 0)
s.eq("the answer names the commit it was read at", answer["as_of"], st.as_of)
s.eq("nobody is waited for", answer["pending_by_agent"], {})
s.write("status.json", out)
s.write("state.json", st.to_json())
raise SystemExit(s.finish())
