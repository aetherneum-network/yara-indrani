"""S05 - an ACK says `by: nadia` but the commit is livia's: the consent does not count as certain."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402
from coord import state as state_mod              # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
log, st = s.state(repo)
forged, = want["doubtful"]

s.against_gold(st, s.expected("gold.json"))
s.eq("the proposal is TO_CONFIRM, not DECIDED", st.status["proposals"], want["proposals"])
s.eq("one violation: author mismatch at the commit of the ACK", st.violations, want["violations"])
s.eq("the ACK is doubtful because of its author", st.doubtful, {forged: ["author"]})
commit = log.commits[want["violations"][0]["commit_index"] - 1]
s.eq("the commit was made by another identity", commit.author_email, want["commit_author"])
entry = next(e for e in log.entries if e.id == forged)
s.eq("while the entry names someone else", entry.by, want["named_in_by"])

doc = state_mod.from_document(log.head_files["COORD.md"])
s.eq("the document alone would say DECIDED", doc.status["proposals"], want["document_alone_says"])

code, out = s.cli("coord.lint", "--repo", repo, "--no-sha")
s.eq("lint exits 3", code, 3)
s.true("lint names both identities", want["named_in_by"] in out and want["commit_author"] in out, out)
s.write("lint.txt", out)

code, out = s.cli("coord.status", "--repo", repo, "--no-sha")
s.true("status asks a human to confirm instead of deciding", "a human: confirm" in out, out)
s.write("status.txt", out)
s.write("state.json", st.to_json())
raise SystemExit(s.finish())
