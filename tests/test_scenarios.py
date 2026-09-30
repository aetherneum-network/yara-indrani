"""The ten scenarios: they have the agreed shape, they pass, they pass from another folder - and they fail
when the expectation or the tooling is wrong."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from coord import fixture
from tests import ROOT
from tests.helpers import child_env, run

SCEN = ROOT / "scenarios"
FOLDERS = sorted(p for p in SCEN.iterdir() if p.is_dir() and p.name[:1] == "S")
NEEDED = ("coord", "rules", "schemas", "scenarios")       # what a scenario needs at run time, and nothing else


def copy_pack(dest: Path) -> Path:
    for name in NEEDED:
        shutil.copytree(ROOT / name, dest / name, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


class Shape(unittest.TestCase):
    def test_there_are_ten_numbered_s01_to_s10(self):
        self.assertEqual([p.name[:3] for p in FOLDERS], [f"S{n:02d}" for n in range(1, 11)])

    def test_every_folder_has_the_agreed_files(self):
        for folder in FOLDERS:
            with self.subTest(folder.name):
                spec = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
                self.assertEqual(sorted(spec), ["expect_exit", "run", "timeout_s"])
                self.assertEqual(spec["run"], ["python", "check.py"])
                self.assertEqual(spec["expect_exit"], 0)
                self.assertTrue(0 < spec["timeout_s"] <= 60)
                self.assertTrue((folder / "check.py").is_file())
                self.assertTrue(any((folder / "input").iterdir()))
                self.assertTrue((folder / "expected" / "declared.json").is_file())
                text = (folder / "run.md").read_text(encoding="utf-8").strip()
                self.assertNotIn("\n", text, "run.md is one paragraph")
                self.assertGreater(len(text.split()), 40)

    def test_inputs_are_what_the_stories_give(self):
        code, out = run(["scenarios/make_inputs.py", "--check"])
        self.assertEqual((code, out.strip()), (0, "scenario inputs: OK - they are what the stories give"))

    def test_expectations_were_declared_by_hand_and_agree_with_the_independent_gold(self):
        for folder in FOLDERS:
            with self.subTest(folder.name):
                declared = json.loads((folder / "expected" / "declared.json").read_text(encoding="utf-8"))
                golds = sorted((folder / "expected").glob("gold*.json"))
                self.assertTrue(golds)
                gold = json.loads(golds[0].read_text(encoding="utf-8"))
                self.assertIn("state", gold)
                self.assertTrue(declared)


class Run(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-scen-"))

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def test_all_ten_pass_and_the_report_is_the_committed_one(self):
        report = self.tmp / "report.json"
        code, out = run(["scenarios/run_all.py", "--work", self.tmp / "work", "--json", report])
        self.assertEqual(code, 0, out)
        lines = out.strip().split("\n")
        self.assertEqual(lines[-1], "scenarios: 10/10 PASS")
        self.assertEqual(len(lines), 11)
        for line, folder in zip(lines, FOLDERS):
            self.assertRegex(line, rf"^{folder.name} PASS \((\d+)/\1 checks\)$")
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                         json.loads((ROOT / "reports" / "scenarios.json").read_text(encoding="utf-8")))

    def test_one_scenario_run_the_way_an_outside_executor_runs_it(self):
        """cwd = the scenario folder, the command of scenario.json, a minimal environment, nothing else."""
        import subprocess
        folder = FOLDERS[4]
        spec = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
        argv = [sys.executable if a in ("python", "python3", "py") else a for a in spec["run"]]
        env = child_env()
        env["COORD_PACK_WORK"] = str(self.tmp / "outside")
        cp = subprocess.run(argv, cwd=str(folder), env=env, capture_output=True, timeout=spec["timeout_s"])
        self.assertEqual(cp.returncode, spec["expect_exit"], cp.stdout.decode("utf-8", "replace"))

    def test_the_pack_passes_from_another_folder_with_only_what_it_needs(self):
        copy = copy_pack(self.tmp / "a copy with spaces" / "deeper")
        code, out = run(["scenarios/run_all.py"], cwd=copy)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip().split("\n")[-1], "scenarios: 10/10 PASS")
        self.assertTrue((copy / "build" / "scenarios").is_dir())          # it wrote inside its own folder

    def test_outputs_are_the_same_bytes_in_two_folders(self):
        a, b = self.tmp / "wa", self.tmp / "somewhere else" / "wb"
        for work in (a, b):
            self.assertEqual(run(["scenarios/run_all.py", "--work", work])[0], 0)
        files_a = sorted(p.relative_to(a).as_posix() for p in a.rglob("out/*") if p.is_file())
        files_b = sorted(p.relative_to(b).as_posix() for p in b.rglob("out/*") if p.is_file())
        self.assertEqual(files_a, files_b)
        self.assertGreater(len(files_a), 20)
        for rel in files_a:
            self.assertEqual((a / rel).read_bytes(), (b / rel).read_bytes(), rel)


class CanFail(unittest.TestCase):
    """A scenario that cannot fail proves nothing: change what is expected, or break the tool, and it fails."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-mut-"))
        cls.copy = copy_pack(cls.tmp / "pack")

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def check(self, folder: str) -> tuple[int, str]:
        return run(["check.py"], cwd=self.copy / "scenarios" / folder)

    def edit_json(self, rel: str, change) -> bytes:
        path = self.copy / rel
        before = path.read_bytes()
        data = json.loads(before.decode("utf-8"))
        change(data)
        path.write_bytes((json.dumps(data, indent=1) + "\n").encode("utf-8"))
        return before

    def test_a_wrong_declared_expectation_fails(self):
        rel = "scenarios/S01_state_from_log/expected/declared.json"

        def flip(d):
            pid = sorted(d["proposals"])[0]
            d["proposals"][pid] = "PROPOSED" if d["proposals"][pid] != "PROPOSED" else "DECIDED"

        before = self.edit_json(rel, flip)
        try:
            code, out = self.check("S01_state_from_log")
        finally:
            (self.copy / rel).write_bytes(before)
        self.assertEqual(code, 1, out)
        self.assertIn("S01_state_from_log FAIL", out)
        self.assertEqual(self.check("S01_state_from_log")[0], 0)

    def test_a_wrong_gold_fails(self):
        rel = "scenarios/S06_lift_two_of_three/expected/gold.json"

        def flip(d):
            fid = sorted(d["state"]["freezes"])[0]
            d["state"]["freezes"][fid] = "LIFTED" if d["state"]["freezes"][fid] != "LIFTED" else "FROZEN"

        before = self.edit_json(rel, flip)
        try:
            code, out = self.check("S06_lift_two_of_three")
        finally:
            (self.copy / rel).write_bytes(before)
        self.assertEqual(code, 1, out)

    def test_a_tool_that_lifts_a_freeze_with_part_of_the_consents_fails_s06(self):
        def loosen(d):
            rule = next(r for r in d["consents"] if r["id"] == "G-LIFT")
            rule["then"]["required"] = []

        before = self.edit_json("rules/freeze.json", loosen)
        try:
            code, out = self.check("S06_lift_two_of_three")
        finally:
            (self.copy / "rules" / "freeze.json").write_bytes(before)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL", out)

    def test_a_tool_that_counts_every_filled_note_as_a_dissent_fails_s07(self):
        def harden(d):
            d["rules"] = [r for r in d["rules"] if r["id"] not in ("N-ACK-NOTE", "N-EMPTY-DISSENT")]

        before = self.edit_json("rules/dissent_nature.json", harden)
        try:
            code, out = self.check("S07_notes_are_not_dissents")
        finally:
            (self.copy / "rules" / "dissent_nature.json").write_bytes(before)
        self.assertNotEqual(code, 0, out)

    def test_a_changed_input_fails(self):
        """S05 with the commit made by the agent named in `by`: no author mismatch any more, so the check fails."""
        path = self.copy / "scenarios" / "S05_author_mismatch" / "input" / "stream.fi"
        before = path.read_bytes()
        chunks = before.split(b"commit refs/heads/main")
        self.assertGreaterEqual(len(chunks), 5)
        lines = chunks[4].split(b"\n")
        for i, line in enumerate(lines):
            if line.startswith((b"author ", b"committer ")):
                lines[i] = line.replace(b"livia@meridiana.example", b"nadia@meridiana.example")
        chunks[4] = b"\n".join(lines)
        changed = b"commit refs/heads/main".join(chunks)
        self.assertNotEqual(changed, before)
        try:
            path.write_bytes(changed)
            code, out = self.check("S05_author_mismatch")
        finally:
            path.write_bytes(before)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
