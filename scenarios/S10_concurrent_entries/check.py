"""S10 - two agents answer at the same time: the second write is refused out loud, then merged; the order
of the entries is the order of the log, whatever the document shows."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402
from coord.parse import parse_doc                 # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()                                   # the shared log holds the proposal only
s.append(repo, "bruno.fi")                        # each agent writes an answer on top of what it has seen
s.append(repo, "carla.fi")


def ids(log) -> list[str]:
    return [e.id for e in log.entries]


code, out = s.cli("coord.submit", "--repo", repo, "--candidate", "submit-bruno")
s.eq("bruno's entry is accepted", [code, out.startswith("submit: OK")], [0, True])
log, st = s.state(repo)
s.eq("after bruno: entries in the log", ids(log), want["after_bruno"]["entries"])
s.subset("after bruno: one consent is not alignment", st.status["proposals"], want["after_bruno"]["proposals"])

code, out = s.cli("coord.submit", "--repo", repo, "--candidate", "submit-carla")
s.eq("carla's entry is refused: exit 3", code, 3)
s.true("the refusal is said in the first line", out.startswith("submit: FAILED"), out)
s.write("rejection.txt", re.sub(r"\b[0-9a-f]{12}\b", "<commit>", out))     # outputs carry no commit hash
log, st = s.state(repo)
w = want["after_rejection"]
s.eq("after the refusal: the log did not move", ids(log), w["entries"])
s.true("after the refusal: carla's entry is not in the shared log", w["not_in_log"] not in ids(log))
s.subset("after the refusal: the proposal is still not aligned", st.status["proposals"], w["proposals"])

s.append(repo, "carla-merge.fi")                  # carla merges what she had not seen, then submits again
code, out = s.cli("coord.submit", "--repo", repo, "--candidate", "submit-carla")
s.eq("after the merge carla's entry is accepted", [code, out.startswith("submit: OK")], [0, True])
log, st = s.state(repo)
w = want["after_merge"]
s.against_gold(st, s.expected("gold.json"), "after the merge")
s.eq("after the merge: entries in log order", ids(log), w["entries"])
s.eq("after the merge: the document shows another order", [e.id for e in parse_doc(log.head_files["COORD.md"]).entries],
     w["document_order"])
s.subset("after the merge: both consents count once", st.status["proposals"], w["proposals"])
s.eq("no entry was lost or doubled", sorted(ids(log)), sorted(set(ids(log))))
s.eq("no violation", st.violations, [])
s.write("state.json", st.to_json())
raise SystemExit(s.finish())
