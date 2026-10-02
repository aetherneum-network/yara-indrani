"""S09 - three conflicts arbitrated by an ordered rule file; one rule is added and only one outcome changes."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import ROOT, Scenario                # noqa: E402
from coord import arbitrate                       # noqa: E402

s = Scenario(__file__)
want = s.expected()
repo = s.repo()
v2_dir = s.input("rules_v2")

_, st1 = s.state(repo)
_, st2 = s.state(repo, v2_dir)
s.against_gold(st1, s.expected("gold.json"))
s.eq("conflict statuses in the log", st1.status["conflicts"], want["conflicts"])
s.eq("no violation", st1.violations, want["violations"])

out1 = {r["conflict"]: [r["rule"], r["outcome"]] for r in arbitrate.records(st1)}
out2 = {r["conflict"]: [r["rule"], r["outcome"]] for r in arbitrate.records(st2)}
s.eq("outcomes under the first rule file", out1, want["rules_v1"])
s.eq("outcomes under the second rule file", out2, want["rules_v2"])
s.eq("exactly one outcome changed", [c for c in out1 if out1[c] != out2[c]], [want["only_change"]])
both = [c for c in out2 if out2[c][1] == "ESCALATE_TO_HUMAN"]
s.true("what no rule covers goes to a human under both rule files", len(both) == 1 and out1[both[0]] == out2[both[0]])

arb = next(r for r in arbitrate.records(st1) if r["recorded_in_log"])
s.eq("the dissent against the arbitration is recorded, not erased", arb["dissents"], [want["recorded_dissent"]])

v1 = json.loads((ROOT / "rules" / "arbitration.json").read_text(encoding="utf-8"))
v2 = json.loads((v2_dir / "arbitration.json").read_text(encoding="utf-8"))
ids1, ids2 = [r["id"] for r in v1["rules"]], [r["id"] for r in v2["rules"]]
s.eq("the second rule file adds one rule and changes none", [i for i in ids2 if i not in ids1], ["R-TIE-FIRST"])
s.eq("the rules it shares are the same, in the same order", [r for r in v2["rules"] if r["id"] in ids1], v1["rules"])

register = s.work / "register"
code, out = s.cli("coord.arbitrate", "--repo", repo, "--register", register)
s.eq("first run: exit 0", code, 0)
first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(register.glob("ARB-*.json"))}
s.eq("first run: three records", sorted(first), ["ARB-0001.json", "ARB-0002.json", "ARB-0003.json"])
text = out
code, out = s.cli("coord.arbitrate", "--repo", repo, "--rules", v2_dir, "--register", register)
after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(register.glob("ARB-*.json"))}
s.eq("second run: one new record, the old ones untouched", {k: after[k] for k in first}, first)
s.eq("second run: the register grew by one", sorted(set(after) - set(first)), ["ARB-0004.json"])
new = json.loads((register / "ARB-0004.json").read_text(encoding="utf-8"))
old = next(r for r in arbitrate.read_register(register) if r["conflict"] == want["only_change"] and r["id"] != new["id"])
s.eq("the new record supersedes the old one and names its rule", [new["conflict"], new["supersedes"], new["rule"], new["rules_version"]],
     [want["only_change"], old["id"], "R-TIE-FIRST", 2])
s.write("arbitrate.txt", text + out)
s.write("register.json", json.dumps(arbitrate.read_register(register), indent=2, sort_keys=True, ensure_ascii=False))
raise SystemExit(s.finish())
