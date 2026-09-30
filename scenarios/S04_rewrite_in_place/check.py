"""S04 - a decided proposal rewritten in place is caught; the same change made by superseding is clean."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import Scenario                      # noqa: E402
from coord import state as state_mod              # noqa: E402

s = Scenario(__file__)
want = s.expected()

for label in ("rewritten", "superseded"):
    repo = s.repo(f"{label}.fi", label)
    log, st = s.state(repo)
    w = want[label]
    s.against_gold(st, s.expected(f"gold_{label}.json"), label)
    s.subset(f"{label}: proposals = declared", st.status["proposals"], w["proposals"])
    s.eq(f"{label}: violations = declared", st.violations, w["violations"])
    code, out = s.cli("coord.lint", "--repo", repo, "--no-sha")
    s.eq(f"{label}: lint exit code", code, 0 if w["lint_ok"] else 3)
    s.write(f"lint_{label}.txt", out)
    s.write(f"state_{label}.json", st.to_json())
    if label == "rewritten":
        (pid, _), = w["proposals"].items()
        s.eq("rewritten: the entry is doubtful because it was modified", st.doubtful, {pid: ["modified"]})
        s.eq("rewritten: before doubt the log would say DECIDED", st.face["proposals"][pid], "DECIDED")
        s.true("rewritten: lint names the rewritten entry and the commit", "commit 6" in out and pid in out, out)
        doc = state_mod.from_document(log.head_files["COORD.md"])
        s.eq("rewritten: the document alone sees nothing wrong", [doc.status["proposals"][pid], doc.violations], ["DECIDED", []])
raise SystemExit(s.finish())
