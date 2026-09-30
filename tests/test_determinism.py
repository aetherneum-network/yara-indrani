"""Two independent rebuilds in two different folders give the same bytes, and the manifests match the disk."""
import re
import tempfile
import unittest
from pathlib import Path

from coord import fixture
from tests import ROOT
from tests.helpers import run
from tools import manifest


def field(out: str, name: str) -> str:
    m = re.search(rf"^{name} sha256=([0-9a-f]{{64}})", out, re.M)
    assert m, out
    return m.group(1)


class Rebuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-rebuild-"))
        cls.a = cls.tmp / "zq-rebuild-one"
        cls.b = cls.tmp / "zq rebuild two" / "deeper"
        cls.out = {}
        for folder in (cls.a, cls.b):
            code, out = run(["tools/rebuild.py", "--out", folder, "--n", "6"])
            assert code == 0, out
            cls.out[folder] = out

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def test_the_bundle_hash_is_the_same(self):
        self.assertEqual(field(self.out[self.a], "bundle"), field(self.out[self.b], "bundle"))
        self.assertEqual(field(self.out[self.a], "corpus"), field(self.out[self.b], "corpus"))

    def test_the_lists_of_files_are_the_same_bytes(self):
        one, two = (self.a / "BUNDLE.sha256").read_bytes(), (self.b / "BUNDLE.sha256").read_bytes()
        self.assertEqual(one, two)
        self.assertGreater(one.count(b"\n"), 60)
        self.assertNotIn(b"\r", one)
        self.assertNotIn(b".git/", one)

    def test_every_listed_file_is_identical(self):
        for line in (self.a / "BUNDLE.sha256").read_text(encoding="utf-8").splitlines():
            rel = line.split("  ", 1)[1]
            self.assertEqual((self.a / rel).read_bytes(), (self.b / rel).read_bytes(), rel)

    def test_no_output_names_the_folder_it_was_built_in_or_a_commit_hash(self):
        for line in (self.a / "BUNDLE.sha256").read_text(encoding="utf-8").splitlines():
            rel = line.split("  ", 1)[1]
            data = (self.a / rel).read_bytes()
            self.assertNotIn(self.a.name.encode(), data, rel)
            self.assertNotIn(str(self.tmp.name).encode(), data, rel)
            if rel.endswith((".state.json", ".status.txt", ".lint.txt")):
                self.assertIsNone(re.search(rb"\b[0-9a-f]{40}\b", data), rel)

    def test_the_scenarios_passed_in_both(self):
        for out in self.out.values():
            self.assertIn("scenarios: 10/10 PASS", out)

    def test_on_one_machine_the_commits_of_the_test_repositories_are_the_same_too(self):
        """Recorded apart from the bundle: commit hashes depend on git, and identity across systems is not claimed."""
        self.assertEqual((self.a / "head_commits.json").read_bytes(), (self.b / "head_commits.json").read_bytes())
        self.assertNotIn("head_commits.json", (self.a / "BUNDLE.sha256").read_text(encoding="utf-8"))


class Manifests(unittest.TestCase):
    def test_the_manifest_is_the_disk(self):
        self.assertEqual(manifest.check(), [])

    def test_the_freeze_list_is_the_disk(self):
        code, out = run(["tools/freeze.py", "--check"])
        self.assertEqual((code, out.strip()), (0, "freeze: OK - the code is the frozen one"))

    def test_frozen_files_are_in_the_manifest_with_the_same_hash(self):
        frozen = dict(reversed(x.split("  ", 1)) for x in (ROOT / "eval" / "FREEZE.sha256").read_text(encoding="utf-8").splitlines())
        listed = dict(reversed(x.split("  ", 1)) for x in (ROOT / manifest.NAME).read_text(encoding="utf-8").splitlines())
        for path, sha in frozen.items():
            self.assertEqual(listed.get(path), sha, path)

    def test_line_endings_do_not_change_a_text_hash_but_streams_are_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            lf, crlf = Path(d) / "a.md", Path(d) / "b.md"
            lf.write_bytes(b"one\ntwo\n")
            crlf.write_bytes(b"one\r\ntwo\r\n")
            self.assertEqual(manifest.digest(lf), manifest.digest(crlf))
            s1, s2 = Path(d) / "a.fi", Path(d) / "b.fi"
            s1.write_bytes(b"one\ntwo\n")
            s2.write_bytes(b"one\r\ntwo\r\n")
            self.assertNotEqual(manifest.digest(s1), manifest.digest(s2))

    def test_build_folders_and_blind_results_are_not_listed(self):
        rels = [p.relative_to(ROOT).as_posix() for p in manifest.listed()]
        self.assertTrue(all(not r.startswith(("build/", ".git/", "corpus/out/", "eval/blind/")) for r in rels))
        self.assertNotIn(manifest.NAME, rels)
        for must in ("README.md", "PROTOCOL.md", "SYNTHETIC.md", "MODEL.md", "CHANGELOG.md", "eval/history.json",
                     "eval/FREEZE.sha256", "reports/scenarios.json", ".github/workflows/ci.yml"):
            self.assertIn(must, rels)


if __name__ == "__main__":
    unittest.main()
