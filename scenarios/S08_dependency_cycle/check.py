"""S08 - A waits for B, B waits for C, C waits for A: the cycle is found and named, with who blocks whom."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402
from coord import deps                            # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
_, st = s.state(repo)
g = deps.graph(st)

s.against_gold(st, s.expected("gold.json"))
s.eq("the three proposals are BLOCKED", st.status["proposals"], want["proposals"])
s.eq("the three blocks are ACTIVE", st.status["blocks"], want["blocks"])
s.eq("one violation: the cycle, at the commit that closes it", st.violations, want["violations"])
s.eq("the cycle is named block by block", g["cycles"], [want["cycle"]])
s.eq("waits-for edges", [[e["on"], e["refs"]] for e in g["edges"]], want["edges"])
s.eq("who blocks whom", [[w["agent"], w["blocks"]] for w in g["who_blocks_whom"]], want["who_blocks_whom"])

code, out = s.cli("coord.deps", "--repo", repo, "--json")
s.eq("the dependency command exits 3 on a cycle", code, 3)
s.eq("and prints the same graph", json.loads(out), g)
s.write("deps.json", out)
code, out = s.cli("coord.deps", "--repo", repo)
s.true("the text report names every block of the cycle", all(b in out for b in want["cycle"]), out)
s.write("deps.txt", out)
raise SystemExit(s.finish())
