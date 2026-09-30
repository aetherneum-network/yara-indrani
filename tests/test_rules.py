"""Ordered rule files: first match wins, exceptions on top; a decision changes by changing a rule."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from coord import arbitrate, rules
from coord.parse import ESCALATE
from tests import ROOT
from tests.helpers import RULES, RepoCase, story


def claim(cid: str, klass: str | None = None, due: str | None = None) -> dict:
    return {"id": cid, "by": cid.split("-")[0], "class": klass, "due": due}


class Matching(unittest.TestCase):
    def test_first_match_wins(self):
        rs = [{"id": "exception", "when": {"type": "ACK", "role": "owner"}}, {"id": "general", "when": {"type": "ACK"}},
              {"id": "default", "when": {}}]
        self.assertEqual(rules.first_match(rs, {"type": "ACK", "role": {"owner", "required"}})["id"], "exception")
        self.assertEqual(rules.first_match(rs, {"type": "ACK", "role": set()})["id"], "general")
        self.assertEqual(rules.first_match(rs, {"type": "DISSENT", "role": set()})["id"], "default")
        self.assertEqual(rules.first_match(list(reversed(rs)), {"type": "ACK", "role": {"owner"}})["id"], "default")

    def test_a_list_means_one_of(self):
        self.assertTrue(rules.matches({"target": ["unblock", "lift"]}, {"target": "lift"}))
        self.assertFalse(rules.matches({"target": ["unblock", "lift"]}, {"target": "proposal"}))
        self.assertTrue(rules.matches({"role": ["owner", "required"]}, {"role": {"required"}}))

    def test_no_match_is_none_not_a_guess(self):
        self.assertIsNone(rules.first_match([{"id": "a", "when": {"type": "ACK"}}], {"type": "LIFT"}))


class RuleFiles(unittest.TestCase):
    def test_every_rule_has_a_unique_id_and_the_files_have_a_version(self):
        for name in rules.FILES:
            data = json.loads((ROOT / "rules" / f"{name}.json").read_text(encoding="utf-8"))
            self.assertIsInstance(data["version"], int)
            ids = [r["id"] for key in ("rules", "consents", "release") for r in data.get(key, [])]
            self.assertTrue(ids)
            self.assertEqual(len(ids), len(set(ids)))

    def test_duplicate_rule_id_is_refused(self):
        tmp = Path(tempfile.mkdtemp(prefix="coordpack-rules-"))
        try:
            shutil.copytree(ROOT / "rules", tmp / "rules")
            data = json.loads((tmp / "rules" / "arbitration.json").read_text(encoding="utf-8"))
            data["rules"].append(dict(data["rules"][0]))
            (tmp / "rules" / "arbitration.json").write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(rules.RuleError):
                rules.load(tmp / "rules")
        finally:
            shutil.rmtree(tmp)

    def test_hash_of_a_rule_file_does_not_depend_on_line_endings(self):
        tmp = Path(tempfile.mkdtemp(prefix="coordpack-rules-"))
        try:
            shutil.copytree(ROOT / "rules", tmp / "rules")
            for f in (tmp / "rules").glob("*.json"):
                f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(rules.load(tmp / "rules").sha256, RULES.sha256)
        finally:
            shutil.rmtree(tmp)

    def test_nature_is_decided_before_counting(self):
        self.assertEqual(RULES.nature("ACK", "formwork inspected"), ("note", "N-ACK-NOTE"))
        self.assertEqual(RULES.nature("ACK", ""), ("none", "N-ACK"))
        self.assertEqual(RULES.nature("DISSENT", "the cure time is too short"), ("dissent", "N-DISSENT"))
        for empty in ("", "none", "None.", "n/a", "No objection", "-"):
            self.assertEqual(RULES.nature("DISSENT", empty), ("none", "N-EMPTY-DISSENT"), empty)

    def test_required_consents_come_from_the_rule_file(self):
        self.assertEqual(RULES.required("decide", "ines", ["bruno", "carla"]), ["bruno", "carla"])
        self.assertEqual(RULES.required("unblock", "bruno", ["carla"]), ["bruno", "carla"])
        self.assertEqual(RULES.required("lift", "ines", ["ines", "bruno"]), ["ines", "bruno"])

    def test_release_gate_rules(self):
        self.assertEqual(RULES.release({"kind": "state", "degraded": True}), ("BLOCKED", "REL-DEGRADED"))
        self.assertEqual(RULES.release({"kind": "freeze", "status": "LIFTED"}), ("OPEN", "REL-FREEZE-LIFTED"))
        self.assertEqual(RULES.release({"kind": "freeze", "status": "TO_CONFIRM"}), ("BLOCKED", "REL-FREEZE"))
        self.assertEqual(RULES.release({"kind": "handoff", "status": "MISMATCH"}), ("BLOCKED", "REL-HANDOFF"))
        self.assertEqual(RULES.release({"kind": "state", "degraded": False}), ("OPEN", "REL-DEFAULT"))


class Arbitration(unittest.TestCase):
    FILE = RULES.arbitration

    def test_each_rule_and_the_uncovered_case(self):
        d = lambda p, q: arbitrate.decide(self.FILE, p, q)
        self.assertEqual(d(claim("a-1", "routine"), claim("b-1", "safety")), ("R-SAFETY", "b-1"))
        self.assertEqual(d(claim("a-1", "deadline", "2026-05-12"), claim("b-1", "deadline", "2026-05-05")), ("R-DUE", "b-1"))
        self.assertEqual(d(claim("a-1"), claim("b-1")), ("R-FIRST", "a-1"))                       # default class: routine
        self.assertEqual(d(claim("a-1", "safety"), claim("b-1", "safety")), ("none", ESCALATE))
        self.assertEqual(d(claim("a-1", "deadline", "2026-05-08"), claim("b-1", "deadline", "2026-05-08")), ("none", ESCALATE))
        self.assertEqual(d(claim("a-1", "deadline"), claim("b-1", "routine")), ("none", ESCALATE))

    def test_safety_is_an_exception_on_top_of_the_due_date(self):
        p, q = claim("a-1", "deadline", "2026-05-01"), claim("b-1", "safety", "2026-06-01")
        self.assertEqual(arbitrate.decide(self.FILE, p, q), ("R-SAFETY", "b-1"))

    def test_changing_the_order_of_the_rules_changes_the_decision(self):
        f = copy.deepcopy(self.FILE)
        f["rules"].insert(0, {"id": "R-ALWAYS-FIRST", "when": {}, "then": {"winner": "first"}})
        self.assertEqual(arbitrate.decide(f, claim("a-1", "routine"), claim("b-1", "safety")), ("R-ALWAYS-FIRST", "a-1"))

    def test_a_rule_that_cannot_name_one_winner_is_an_error_not_a_guess(self):
        f = {"rules": [{"id": "R-BAD", "when": {}, "then": {"winner": {"lowest": "due"}}}]}
        with self.assertRaises(rules.RuleError):
            arbitrate.decide(f, claim("a-1"), claim("b-1"))
        with self.assertRaises(rules.RuleError):
            arbitrate.decide({"rules": [{"id": "R", "when": {"sometimes": "due"}, "then": {"winner": "first"}}]}, claim("a-1"), claim("b-1"))


class OneRuleOneDifference(RepoCase):
    """Changing one rule changes exactly the outcomes that rule covers (the rule is fixed, never the output)."""

    def test_unblock_rule_without_the_blocker(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        blk = b.block("carla", p, to=["dario"], text="the pump is booked elsewhere")
        u = b.unblock("ines", blk)
        b.ack("dario", u)
        repo = self.repo(b)
        from coord import gitlog, state as state_mod
        log = gitlog.read(repo)
        before = state_mod.derive(log, RULES)
        self.assertEqual(before.status["blocks"][blk], "ACTIVE")                    # carla, who blocked, has not consented
        changed = copy.deepcopy(RULES.freeze)
        next(r for r in changed["consents"] if r["id"] == "G-UNBLOCK")["then"]["required"] = ["to"]
        loose = rules.RuleSet(RULES.transitions, changed, RULES.dissent_nature, RULES.arbitration, RULES.sha256, RULES.version)
        after = state_mod.derive(gitlog.read(repo), loose)
        self.assertEqual(after.status["blocks"][blk], "REMOVED")
        diff = [(k, o) for k in before.status for o in before.status[k] if before.status[k][o] != after.status[k][o]]
        self.assertEqual(sorted(diff), [("blocks", blk), ("proposals", p)])


if __name__ == "__main__":
    unittest.main()
