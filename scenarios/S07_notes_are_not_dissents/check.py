"""S07 - twenty filled notes, six true dissents, three empty ones: each is classified before it is counted."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
_, st = s.state(repo)
resp = st.details["responses"]

s.against_gold(st, s.expected("gold.json"))
s.eq("filled notes", resp["by_nature"]["note"], want["notes"])
s.eq("true dissents", resp["by_nature"]["dissent"], want["true_dissents"])
s.true("a note was never counted as a dissent",
       all(e["nature"] == "note" for e in resp["entries"].values() if e["rule"] == "N-ACK-NOTE"))
empty = sorted(i for i, e in resp["entries"].items() if e["type"] == "DISSENT" and e["nature"] == "none")
s.eq("dissents with nothing in them", len(empty), want["empty_dissents"])
s.true("an empty dissent opens no dispute", not set(empty) & set(st.status["disputes"]))
s.eq("disputes = the six true dissents, two answered", st.status["disputes"], want["disputes"])
s.eq("answered", sum(v == "ANSWERED" for v in st.status["disputes"].values()), want["answered"])
s.eq("open", sum(v == "OPEN" for v in st.status["disputes"].values()), want["open_disputes"])
s.eq("proposals = declared (an answered dissent is still not a consent, an empty one neither)",
     st.status["proposals"], want["proposals"])
s.eq("no violation", st.violations, want["violations"])

code, out = s.cli("coord.status", "--repo", repo, "--json", "--no-sha")
answer = json.loads(out)
s.eq("status lists the open disputes", answer["open_disputes"], sorted(k for k, v in want["disputes"].items() if v == "OPEN"))
s.eq("status counts by nature", answer["responses_by_nature"], resp["by_nature"])
s.write("status.json", out)
s.write("responses.json", json.dumps(resp, indent=2, sort_keys=True, ensure_ascii=False))
raise SystemExit(s.finish())
