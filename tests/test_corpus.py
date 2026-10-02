"""The synthetic corpus: generated the same way every time, scored against a gold that shares no code with
the tooling - and a scorer that is shown to fail when the tooling is wrong."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from coord import fixture, gitlog, rules, state as state_mod
from corpus import generate, reference_reducer
from eval import score
from tests import ROOT
from tests.helpers import RULES

DEV = generate.AUTHOR_SEEDS["dev"]


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-corpus-"))

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def test_same_seed_same_bytes_in_two_folders(self):
        a = generate.generate(DEV, self.tmp / "a", "standard", 8)
        b = generate.generate(DEV, self.tmp / "deeper" / "b", "standard", 8)
        self.assertEqual(generate.digest(a), generate.digest(b))
        for row in a["stories"]:
            for name in ("events.json", "stream.fi", "gold.json"):
                self.assertEqual((self.tmp / "a" / row["id"] / name).read_bytes(),
                                 (self.tmp / "deeper" / "b" / row["id"] / name).read_bytes())

    def test_another_seed_is_another_corpus(self):
        a = generate.generate(DEV, self.tmp / "c", "standard", 4)
        b = generate.generate(DEV + 7919, self.tmp / "d", "standard", 4)
        self.assertNotEqual(generate.digest(a), generate.digest(b))

    def test_stories_have_the_declared_shape(self):
        index = generate.generate(DEV, self.tmp / "e", "standard", 16)
        self.assertEqual(sum(1 for r in index["stories"] if r["clean"]), 4)          # one story in four is clean
        for row in index["stories"]:
            events = json.loads((self.tmp / "e" / row["id"] / "events.json").read_text(encoding="utf-8"))
            self.assertTrue(20 <= len(events) <= 60, len(events))
            agents = events[0]["agents"]
            self.assertTrue(3 <= len(agents) <= 6)
            self.assertTrue(all(a["email"].endswith(".example") for a in agents))
            gold = json.loads((self.tmp / "e" / row["id"] / "gold.json").read_text(encoding="utf-8"))
            self.assertEqual(bool(gold["violations"]), not row["clean"])

    def test_stress_profile_changes_the_rendering_not_the_gold(self):
        std = generate.generate(DEV, self.tmp / "f", "standard", 6)
        stress = generate.generate(DEV, self.tmp / "g", "stress", 6)
        self.assertNotEqual(generate.digest(std), generate.digest(stress))
        differ = 0
        for row in std["stories"]:
            gold_a = json.loads((self.tmp / "f" / row["id"] / "gold.json").read_text(encoding="utf-8"))
            gold_b = json.loads((self.tmp / "g" / row["id"] / "gold.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(gold_a["state"]), sorted(gold_b["state"]))
            differ += (self.tmp / "f" / row["id"] / "stream.fi").read_bytes() != (self.tmp / "g" / row["id"] / "stream.fi").read_bytes()
        self.assertGreater(differ, 0)

    def test_the_reference_reducer_shares_no_code_with_the_tooling(self):
        import ast
        tree = ast.parse((ROOT / "corpus" / "reference_reducer.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertNotIn("coord", imported)
        self.assertNotIn("subprocess", imported)

    def test_the_reference_reducer_refuses_what_it_does_not_cover(self):
        from tests.helpers import story
        b = story()
        b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", "ines-9")
        with self.assertRaises(reference_reducer.Unsupported):
            reference_reducer.reduce_events(b.events)


class DevCorpus(unittest.TestCase):
    """The whole dev corpus (seed 20260930, 120 stories): log against gold, log against document."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-dev-"))
        cls.index = generate.generate(DEV, cls.tmp / "corpus", "standard", generate.DEFAULT_N)
        cls.res = {"suite": "dev", **score.score_corpus(cls.tmp / "corpus", cls.tmp / "repos", cls.index)}

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def test_results_are_the_committed_ones(self):
        committed = json.loads((ROOT / "eval" / "results_dev.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(self.res)), committed)

    def test_every_object_of_every_story_has_the_gold_status(self):
        o = self.res["objects"]["all"]
        self.assertEqual((o["exact"], o["gold"], o["extra"]), (o["gold"], o["gold"], 0))
        self.assertGreater(o["gold"], 1500)
        self.assertEqual(self.res["stories_exact"], 120)

    def test_the_never_event_did_not_happen(self):
        self.assertEqual((self.res["never_events"], self.res["wrong_assertions"]), (0, 0))
        self.assertEqual(self.res["release_gate_exact"], 120)

    def test_every_violation_class_is_planted_and_found(self):
        for cls, v in self.res["violations"].items():
            if cls != "all":
                self.assertGreaterEqual(v["gold"], 10, cls)
            self.assertEqual((v["tp"], v["fp"], v["fn"]), (v["gold"], 0, 0), cls)

    def test_doubt_is_reported_exactly_where_the_gold_has_it(self):
        o = self.res["objects"]["all"]
        self.assertEqual((o["tool_to_confirm"], o["tool_only_to_confirm"]), (o["gold_to_confirm"], 0))
        self.assertGreater(o["gold_to_confirm"], 0)
        self.assertEqual(self.res["structural_findings"], {})

    def test_log_and_document_agree_on_clean_stories_and_the_document_is_fooled_on_others(self):
        d = self.res["document_vs_log"]
        self.assertEqual((d["clean_agree"], d["clean_stories"]), (30, 30))
        self.assertGreater(d["planted_disagree"], 30)           # the document alone misses what only the log shows


class ScorerCanFail(unittest.TestCase):
    """A perfect score means nothing if the scorer cannot give a bad one. Here the tooling is made wrong on
    purpose (one rule changed: a decision needs nobody's consent) and the scorer must say so."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-mutant-"))
        cls.index = generate.generate(DEV, cls.tmp / "corpus", "standard", 24)

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def score_with(self, ruleset) -> dict:
        total = {"never": 0, "wrong": 0, "fn": 0, "fp": 0, "exact": 0}
        for row in self.index["stories"]:
            d = self.tmp / "corpus" / row["id"]
            gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
            log = gitlog.read(fixture.build_repo((d / "stream.fi").read_bytes(), self.tmp / "r.git"))
            st = state_mod.derive(log, ruleset)
            r = score.score_story(gold, st, state_mod.from_document(log.head_files["COORD.md"], ruleset))
            total["never"] += len(r["never_events"])
            total["wrong"] += len(r["wrong_assertions"])
            total["fn"] += len(r["violations"]["fn"])
            total["fp"] += len(r["violations"]["fp"])
            total["exact"] += r["exact"]
        return total

    def test_the_real_rules_score_clean_on_this_subset(self):
        self.assertEqual(self.score_with(RULES), {"never": 0, "wrong": 0, "fn": 0, "fp": 0, "exact": 24})

    def test_a_tool_that_decides_without_consents_is_caught(self):
        freeze = copy.deepcopy(RULES.freeze)
        next(r for r in freeze["consents"] if r["id"] == "G-DECIDE")["then"]["required"] = []
        mutant = rules.RuleSet(RULES.transitions, freeze, RULES.dissent_nature, RULES.arbitration, RULES.sha256, RULES.version)
        t = self.score_with(mutant)
        self.assertGreater(t["never"], 0)
        self.assertGreater(t["fn"], 0)                          # the V05 it no longer reports
        self.assertLess(t["exact"], 24)

    def test_a_tool_that_ignores_the_author_of_a_commit_is_caught(self):
        original = gitlog.extract

        def blind_to_authors(commits):
            log = original(commits)
            log.findings = [f for f in log.findings if f.cls != "V02"]
            for e in log.entries:
                e.doubt.discard("author")
            return log

        gitlog.extract = blind_to_authors
        try:
            t = self.score_with(RULES)
        finally:
            gitlog.extract = original
        self.assertGreater(t["wrong"], 0)
        self.assertGreater(t["fn"], 0)

    def test_a_wrong_gold_is_a_mismatch(self):
        row = self.index["stories"][0]
        d = self.tmp / "corpus" / row["id"]
        gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
        pid = next(iter(gold["state"]["proposals"]))
        gold["state"]["proposals"][pid] = "PROPOSED" if gold["state"]["proposals"][pid] != "PROPOSED" else "DECIDED"
        log = gitlog.read(fixture.build_repo((d / "stream.fi").read_bytes(), self.tmp / "r2.git"))
        st = state_mod.derive(log, RULES)
        r = score.score_story(gold, st, state_mod.from_document(log.head_files["COORD.md"], RULES))
        self.assertFalse(r["exact"])
        self.assertEqual(len(r["mismatches"]), 1)


class BlindGuards(unittest.TestCase):
    def run_score(self, *args):
        from tests.helpers import run
        return run(["eval/score.py", *args])

    def test_the_blind_suite_refuses_the_seeds_the_author_used(self):
        for seed in generate.AUTHOR_SEEDS.values():
            code, out = self.run_score("--suite", "blind", "--seed", seed, "--runner", "test")
            self.assertEqual(code, 2)
            self.assertIn("was used by the author", out)

    def test_the_blind_suite_needs_a_seed_and_a_runner(self):
        self.assertEqual(self.run_score("--suite", "blind", "--seed", "5")[0], 2)
        self.assertEqual(self.run_score("--suite", "blind", "--runner", "test")[0], 2)

    def test_dev_and_stress_seeds_cannot_be_changed_from_the_command_line(self):
        self.assertEqual(self.run_score("--suite", "dev", "--seed", "5")[0], 2)

    def test_frozen_code_is_the_code_on_disk(self):
        self.assertEqual(score.check_frozen(), [])

    def test_a_changed_file_is_noticed(self):
        listing = ROOT / "eval" / "FREEZE.sha256"
        lines = listing.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 20)
        paths = [line.split("  ", 1)[1] for line in lines]
        for must in ("coord/state.py", "corpus/reference_reducer.py", "rules/transitions.json", "PROTOCOL.md", "eval/score.py"):
            self.assertIn(must, paths)
        self.assertTrue(all(not p.startswith(("tests/", "README", "eval/blind/")) for p in paths))

    def test_no_blind_seed_was_run_by_the_author(self):
        blind = ROOT / "eval" / "blind"
        found = [p.name for p in blind.glob("*.json")] if blind.is_dir() else []
        history = json.loads((ROOT / "eval" / "history.json").read_text(encoding="utf-8"))
        recorded = [r.get("output") for r in history["runs"] if r.get("suite", "").startswith("blind")]
        self.assertEqual(sorted(found), sorted(Path(o).name for o in recorded if o),
                         "every blind result on disk must be recorded in eval/history.json with who ran it")


if __name__ == "__main__":
    unittest.main()
