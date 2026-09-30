"""The documents say what the repository shows, and no more: claims point at things that exist, numbers
in the README are the numbers of the result files, the profile was edited only where declared, and the
sentences awaiting legal review are exactly as they were."""
import hashlib
import json
import re
import unittest

from tests import ROOT
from tools import manifest

START, END = "<!-- proof-pack:start -->", "<!-- proof-pack:end -->"
ORIGINAL_README_SHA256 = "158e4c9bf21b476becce1eb844cc75511c5b84eff1e313130d6d49a60df1cc59"        # the profile page before this pack, LF endings
AWAITING_LEGAL = (
    "The thesis formalizes the coordination protocol Yara co-authored with Aetherneum and Riku across multiple ship cycles.",
    "Her masterpiece is the platform's coordination document — many cycles of async coordination between agents, where "
    "every decision is reconstructible from `git log` alone, with not a single meeting.",
    "Authored the platform coordination document — many cycles, zero meetings, every decision reconstructible from "
    "`git log` alone",
)
REWORDED = (
    ("No meetings. No standups.", "The protocol does not require meetings."),
    ("The status of any project: visible to her in 30 seconds via `git log`.",
     "The status of a project: derived from the log with one command."),
)
REMOVED = (
    " Has reduced organizational entropy with one elegantly-named markdown file.",
    " Each invocation is recorded in the git history of the placement repository; the trail is auditable end-to-end.",
)
CLAIMS = {
    "A1": ("every cycle is a markdown commit, every commit is a state transition, every state transition is verifiable "
           "from `git log` alone", {"S01", "S04", "S10"}),
    "A2": ("Freeze protocols - when to halt ship, when to lift, who needs to ack", {"S06"}),
    "A3": ("Dependency mapping - knowing which agent's work blocks whose, before they do", {"S08"}),
    "A4": ("Conflict resolution - between agents with overlapping placements", {"S07", "S09"}),
    "A5": ("Status reporting - terse, factual, structured, no fluff", {"S03"}),
    "A6": ("Ship arc tracking - build numbering, tag conventions, milestone declaration", {"S02"}),
}


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("—", "-").replace("*", ""))


def section(readme: str) -> str:
    return readme[readme.index(START):readme.index(END)]


class Profile(unittest.TestCase):
    def test_sentences_awaiting_legal_review_are_exactly_as_they_were(self):
        readme = read("README.md")
        for sentence in AWAITING_LEGAL:
            self.assertEqual(readme.count(sentence), 1, sentence)
        self.assertEqual(readme.count("platform"), 2)            # the two sentences above, and nowhere else
        self.assertNotIn("platform", section(readme))

    def test_the_profile_was_changed_only_where_declared(self):
        """Take the pack's additions out and put the four declared sentences back: what is left is the old page."""
        readme = read("README.md")
        banner, rest = readme.split("\n\n", 1)
        self.assertTrue(banner.startswith("**SYNTHETIC - "))
        a, b = rest.index(START), rest.index(END) + len(END)
        self.assertEqual(rest[b:b + 2], "\n\n")
        old = rest[:a] + rest[b + 2:]
        for before, after in REWORDED:
            self.assertEqual(old.count(after), 1, after)
            old = old.replace(after, before)
        old = old.replace('aligned in five minutes." The', 'aligned in five minutes."' + REMOVED[0] + " The", 1)
        old = old.replace("`requirements-analyst`.", "`requirements-analyst`." + REMOVED[1], 1)
        self.assertEqual(hashlib.sha256(old.encode("utf-8")).hexdigest(), ORIGINAL_README_SHA256)

    def test_removed_and_reworded_sentences_are_gone_from_the_profile_and_kept_in_the_changelog(self):
        readme, changelog, claims = read("README.md"), read("CHANGELOG.md"), read("CLAIMS.md")
        for before, after in REWORDED:
            self.assertNotIn(before, readme)
            self.assertIn(after, readme)
            for doc in (changelog, claims):
                self.assertIn(before, doc)
                self.assertIn(after, doc)
        for sentence in REMOVED:
            self.assertNotIn(sentence.strip(), readme)
            self.assertIn(sentence.strip(), changelog)
            self.assertIn(sentence.strip(), claims)

    def test_the_author_is_declared_synthetic(self):
        sec = section(read("README.md"))
        self.assertIn("synthetic AI agent", sec)
        self.assertIn("not by a person", sec)
        self.assertIn("Claude Opus 5.5", sec)


class Claims(unittest.TestCase):
    def test_each_claim_is_a_sentence_of_the_profile_and_names_its_scenarios(self):
        readme, claims = plain(read("README.md")), read("CLAIMS.md")
        rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| (A\d) \|.*$", claims, re.M)}
        self.assertEqual(sorted(rows), sorted(CLAIMS))
        for key, (sentence, scenarios) in CLAIMS.items():
            self.assertIn(plain(sentence), readme, key)
            self.assertIn(sentence, rows[key], key)
            self.assertEqual(set(re.findall(r"S\d\d", rows[key].split("|")[3])), scenarios, key)

    def test_everything_a_claim_points_at_exists(self):
        claims = read("CLAIMS.md")
        folders = {p.name[:3] for p in (ROOT / "scenarios").iterdir() if p.is_dir() and p.name.startswith("S")}
        for s in set(re.findall(r"\bS\d\d\b", claims)):
            self.assertIn(s, folders)
        paths = set(re.findall(r"`((?:tests|coord|rules|eval|reports|tools|schemas|templates|scenarios|\.github)/[\w./-]*\w|"
                               r"[A-Z]+\.md|MANIFEST\.sha256)`", claims))
        self.assertGreater(len(paths), 20)
        for rel in paths:
            if rel == "reports/scan.json":
                self.assertFalse((ROOT / rel).exists(), "declared as not produced")
            else:
                self.assertTrue((ROOT / rel).exists(), rel)

    def test_the_three_answers_and_the_limits_are_there(self):
        claims = read("CLAIMS.md")
        for heading in ("## 1. Demonstrated", "## 2. Awaiting legal review - not touched", "## 3. Not demonstrated: out of v2.0",
                        "## 5. Known limits"):
            self.assertIn(heading, claims)
        part = claims[claims.index("## 2."):claims.index("## 3.")]
        for sentence in AWAITING_LEGAL:
            self.assertIn(sentence, part)
        self.assertEqual(claims.count("platform"), 2)
        for req in range(1, 11):
            self.assertRegex(claims, rf"(?m)^\| E{req} \|")

    def test_test_names_quoted_in_the_claims_exist(self):
        claims = read("CLAIMS.md")
        for module, cls in (("tests/test_corpus.py", "ScorerCanFail"), ("tests/test_scenarios.py", "CanFail")):
            self.assertIn(cls, claims)
            self.assertIn(f"class {cls}(", read(module))
        never = read("tests/test_never_event.py")
        self.assertEqual(len(re.findall(r"^    def test_", never, re.M)), 27)
        self.assertIn("27 directions", claims)


class Numbers(unittest.TestCase):
    """Every number of the README section is read again from the file it names."""

    @classmethod
    def setUpClass(cls):
        cls.sec = section(read("README.md"))
        cls.dev = json.loads(read("eval/results_dev.json"))
        cls.history = json.loads(read("eval/history.json"))
        cls.scen = json.loads(read("reports/scenarios.json"))
        cls.rebuild = json.loads(read("reports/rebuild.json"))

    def test_dev_corpus(self):
        d, o, v = self.dev, self.dev["objects"]["all"], self.dev["violations"]["all"]
        self.assertEqual(d["seed"], 20260930)
        self.assertIn(f"{o['exact']} of {o['gold']} ({d['stories']} stories, {d['commits']} commits)", self.sec)
        self.assertIn(f"{v['tp']} found of {v['gold']} planted, {v['fp']} false reports", self.sec)
        self.assertIn(f"{o['tool_to_confirm']} `TO_CONFIRM`, the {o['gold_to_confirm']} of the gold", self.sec)
        self.assertIn(f"| {d['wrong_assertions']} / {d['never_events']} |", self.sec)
        dl = d["document_vs_log"]
        self.assertIn(f"agree on {dl['clean_agree']} of {dl['clean_stories']} clean stories", self.sec)
        self.assertIn(f"differ on {dl['planted_disagree']} of {dl['planted_stories']} stories with a planted defect", self.sec)
        self.assertEqual((o["exact"], v["fn"], d["never_events"]), (o["gold"], 0, 0))

    def test_stress_diagnosis_first_run_is_reported_as_it_was(self):
        runs = {r["n"]: r for r in self.history["runs"]}
        first, after = runs[2]["result"], runs[3]["result"]
        self.assertEqual((first["suite"], first["seed"]), ("stress-diag", 20261002))
        o = first["objects"]["all"]
        self.assertLess(o["exact"], o["gold"] // 2)                       # the bad run is in the history, verbatim
        self.assertIn(f"{o['exact']} of {o['gold']} objects, {first['stories_exact']} of {first['stories']} stories; "
                      f"{first['wrong_assertions']} wrong assertions", self.sec)
        o2 = after["objects"]["all"]
        self.assertIn(f"{o2['exact']} of {o2['gold']} - **not evidence**", self.sec)
        self.assertIn("NOT EVIDENCE", runs[3]["note"])

    def test_scenarios_and_tests(self):
        checks = sum(s["checks"] for s in self.scen["scenarios"])
        self.assertEqual((self.scen["passed"], self.scen["total"]), (10, 10))
        self.assertIn(f"10/10 PASS ({checks} checks)", self.sec)
        count = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT)).countTestCases()
        self.assertIn(f"| {count} tests, OK |", self.sec)

    def test_rebuild(self):
        r = self.rebuild
        a, b = r["runs"]
        self.assertEqual(a["bundle_sha256"], b["bundle_sha256"])
        self.assertNotEqual(a["folder"], b["folder"])
        self.assertTrue(r["identical"])
        self.assertIn(f"{a['files']} files, sha256 `{a['bundle_sha256']}`", self.sec)
        self.assertEqual(r["corpus_sha256"], self.dev["corpus_sha256"])
        self.assertIn("[TO CONFIRM]", r["commit_hashes_across_systems"])

    def test_fewer_than_five_commands_and_each_one_exists(self):
        block = re.search(r"```\n(.*?)```", self.sec, re.S).group(1).strip().split("\n")
        self.assertLess(len(block), 5)
        for line in block:
            self.assertTrue(line.startswith("python "))
            script = re.search(r"(scenarios|eval|tools)/\w+\.py", line)
            if script:
                self.assertTrue((ROOT / script.group(0)).is_file())

    def test_what_is_not_demonstrated_is_said(self):
        self.assertIn("### What is NOT demonstrated", self.sec)
        for must in ("real team", "blind run", "never been executed", "awaiting legal review", "one machine"):
            self.assertIn(must, self.sec)
        self.assertIn("Standard library only", self.sec)


class Blind(unittest.TestCase):
    def test_the_protocol_gives_the_exact_commands_and_says_it_was_not_run(self):
        text = read("eval/BLIND_PROTOCOL.md")
        for must in ('python eval/score.py --suite blind --seed N --profile standard --runner "NAME"',
                     'python eval/score.py --suite blind --seed N --profile stress --runner "NAME"',
                     'python eval/blind_hand.py --repo blind-hand --declared declared.json --runner "NAME"',
                     "python tools/freeze.py --check", "git init --initial-branch=main blind-hand",
                     "not done", "v2.0.0-freeze", "20260930", "20261002"):
            self.assertIn(must, text)

    def test_the_history_holds_no_blind_result(self):
        history = json.loads(read("eval/history.json"))
        self.assertEqual([r["suite"] for r in history["runs"]],
                         ["dev", "stress-diag", "stress-diag", "dev", "stress-diag-ablation"])
        self.assertEqual(history["seeds_seen_by_the_author"], {"dev": 20260930, "stress-diag": 20261002})

    def test_documents_added_after_the_freeze_are_in_the_manifest(self):
        rels = {p.relative_to(ROOT).as_posix() for p in manifest.listed()}
        for must in ("CLAIMS.md", "eval/BLIND_PROTOCOL.md", "reports/rebuild.json", "tests/test_docs.py"):
            self.assertIn(must, rels)


if __name__ == "__main__":
    unittest.main()
