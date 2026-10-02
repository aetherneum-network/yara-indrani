"""What the repository must not contain: paths and names of any real machine, domains that are not
fictional, broken encodings - and what it must contain: the SYNTHETIC banner, first line of the README.

This file is the only one not scanned by the word check: the forbidden names are kept here as hashes, so
that the repository does not contain them even as a list of things to avoid.
"""
import hashlib
import re
import unittest
from pathlib import Path

from tests import ROOT
from tools import manifest

BINARY = (".jpg", ".png")
CHECKOUT_DEPENDENT = ("README.md", "LICENSE")       # older than the pack: line endings on disk depend on the checkout
FORBIDDEN_WORDS = {"9ec51d5e3288cdd2", "7f5b365dc74983fa", "612426d632cd433b", "84de87b864da8087", "f86c8d340dabc937",
                   "f81630cdc129910f"}              # first 16 hex digits of sha256(lower-case word)
DRIVE = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?=[A-Za-z_.])")
UNIX = re.compile(r"(?<![\w.])/(?:opt|var|home|Users|etc|root|mnt|srv|tmp)/")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})")
URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
OWN_EMAILS = {"yara.indrani@aetherneum.com", "noreply@anthropic.com"}
OWN_HOSTS = {"aetherneum.com", "university.aetherneum.com"}
BANNER = ("**SYNTHETIC - Yara Indrani is a synthetic alumna (an AI agent) of Aetherneum University, not a person and not a "
          "certified project manager. Every team, agent, company, build number and decision in this repository is "
          "fictitious. The coordination cycles were written for this repository: they are not excerpts, sanitized or "
          "otherwise, of any real project's documents.**")


def text_files() -> list[tuple[str, str]]:
    out = []
    for p in manifest.listed():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix in BINARY or rel == "tests/test_hygiene.py":
            continue
        out.append((rel, p.read_bytes().decode("utf-8")))          # a file that is not UTF-8 fails here, by name
    return out


class Hygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = text_files()

    def test_there_are_files_to_scan(self):
        self.assertGreater(len(self.files), 120)

    def test_no_path_of_a_real_machine(self):
        for rel, text in self.files:
            with self.subTest(rel):
                self.assertIsNone(DRIVE.search(text), DRIVE.search(text))
                self.assertIsNone(UNIX.search(text), UNIX.search(text))
                self.assertNotIn("\\Users\\", text)
                self.assertNotIn("AppData", text)

    def test_no_forbidden_name(self):
        for rel, text in self.files:
            words = set(re.findall(r"[a-z0-9]+", (rel + " " + text).lower()))
            hit = [w for w in words if hashlib.sha256(w.encode()).hexdigest()[:16] in FORBIDDEN_WORDS]
            self.assertEqual(hit, [], rel)

    def test_no_ip_address(self):
        for rel, text in self.files:
            with self.subTest(rel):
                self.assertIsNone(IPV4.search(text), IPV4.search(text))

    def test_every_email_is_fictional_or_the_declared_author(self):
        seen = 0
        for rel, text in self.files:
            for m in EMAIL.finditer(text):
                seen += 1
                if m.group(0) not in OWN_EMAILS:
                    self.assertTrue(m.group(1).endswith(".example"), f"{rel}: {m.group(0)}")
        self.assertGreater(seen, 200)

    def test_every_link_points_to_the_university_only(self):
        for rel, text in self.files:
            for m in URL.finditer(text):
                host = m.group(1).rstrip(".")
                self.assertTrue(host in OWN_HOSTS or host.endswith(".example"), f"{rel}: {host}")

    def test_links_to_the_university_are_only_in_the_profile_page(self):
        for rel, text in self.files:
            if rel != "README.md":
                self.assertIsNone(URL.search(text), rel)

    def test_text_is_utf8_without_bom_and_with_lf_endings(self):
        for rel, text in self.files:
            with self.subTest(rel):
                self.assertFalse(text.startswith("\ufeff"))
                self.assertNotIn("\ufffd", text)
                if rel not in CHECKOUT_DEPENDENT:
                    self.assertNotIn("\r", text)
                if text and not rel.endswith(".fi"):
                    self.assertTrue(text.endswith("\n"), "ends with a newline")

    def test_paths_are_short_and_plain(self):
        for rel, _ in self.files:
            self.assertLess(len(rel), 100, rel)
            self.assertRegex(rel, r"^[A-Za-z0-9_./-]+$")

    def test_git_attributes_keep_lf_and_streams_as_bytes(self):
        lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").split("\n")
        self.assertIn("* text=auto eol=lf", lines)
        self.assertIn("*.fi -text", lines)

    def test_generated_folders_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        for must in ("build/", "corpus/out/", "__pycache__/"):
            self.assertIn(must, ignore)


class Declared(unittest.TestCase):
    def test_the_banner_is_the_first_line_of_the_readme(self):
        first = (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")[0]
        self.assertEqual(first, BANNER)

    def test_synthetic_and_model_statements_exist(self):
        synthetic = (ROOT / "SYNTHETIC.md").read_text(encoding="utf-8")
        model = (ROOT / "MODEL.md").read_text(encoding="utf-8")
        self.assertIn("fictitious", synthetic)
        self.assertIn(".example", synthetic)
        for must in ("claude-opus-5-5", "claude-fable-5-1", "No model is called"):
            self.assertIn(must, model)

    def test_company_names_in_the_documents_are_the_invented_ones(self):
        from corpus import world
        names = {c["company"] for c in world.COMPANIES.values()}
        self.assertEqual(names, {"Cantiere Portoluna S.r.l.", "Editrice Meridiana S.r.l.", "Laboratorio Ottico Fiordaliso"})
        synthetic = (ROOT / "SYNTHETIC.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(name, synthetic)

    def test_every_agent_of_the_invented_world_has_a_fictional_address(self):
        from corpus import world
        for key in world.COMPANIES:
            _, agents = world.team(key, [a[0] for a in world.COMPANIES[key]["agents"][:3]])
            for a in agents:
                self.assertTrue(a["email"].endswith(".example"))


if __name__ == "__main__":
    unittest.main()
