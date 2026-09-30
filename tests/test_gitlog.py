"""Reading the history: isolation of the git calls, log order across branches, what each commit added."""
import tempfile
import unittest
from pathlib import Path

from coord import fixture, gitlog
from corpus import render
from tests.helpers import RepoCase, story


class Isolation(unittest.TestCase):
    def test_git_environment_is_built_from_scratch(self):
        env = fixture.git_env()
        self.assertEqual(env["GIT_ALLOW_PROTOCOL"], "file")             # no network transport can be used
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], env["GIT_CONFIG_SYSTEM"])
        self.assertEqual(Path(env["GIT_CONFIG_GLOBAL"]).read_bytes(), b"")
        for leaked in ("GIT_DIR", "GIT_WORK_TREE", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "SSH_AUTH_SOCK", "GIT_ASKPASS"):
            self.assertNotIn(leaked, env)

    def test_minimum_git_version(self):
        self.assertGreaterEqual(fixture.require_git()[:2], fixture.MIN_GIT)

    def test_not_a_repository(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(fixture.GitError):
                fixture.git_dir_of(empty)


class Reading(RepoCase):
    def test_every_commit_has_its_author_time_and_index(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        log = gitlog.read(self.repo(b))
        self.assertEqual([c.index for c in log.commits], [1, 2, 3])
        self.assertEqual([c.author_email for c in log.commits],
                         ["ines@portoluna.example", "ines@portoluna.example", "bruno@portoluna.example"])
        self.assertEqual([(e.id, e.commit_index, e.author_email) for e in log.entries],
                         [(p, 2, "ines@portoluna.example"), ("bruno-1", 3, "bruno@portoluna.example")])
        self.assertEqual(log.ancestors[3], frozenset({1, 2}))
        self.assertEqual(log.findings, [])
        self.assertTrue(all(c.author_email.endswith(".example") for c in log.commits))

    def test_two_builds_of_the_same_story_give_the_same_commits(self):
        b = story()
        b.propose("ines", ["bruno"], "Pour slab B2.")
        one, two = self.repo(b), self.repo(b)
        self.assertNotEqual(one, two)
        self.assertEqual(fixture.head_sha(one), fixture.head_sha(two))

    def test_branches_are_ordered_by_commit_time_in_utc_not_by_local_clock(self):
        b = story(["ines", "bruno", "carla"])
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        base = b.tip
        first = b.ack("carla", p, parent=base, as_of="2026-02-02T23:59:00+01:00")     # earlier commit, later wall clock
        n1 = b.tip
        second = b.ack("bruno", p, parent=base, as_of="2026-02-02T00:01:00+01:00")
        n2 = b.tip
        b.merge("bruno", [n2, n1])
        log = gitlog.read(self.repo(b))
        self.assertEqual([e.id for e in log.entries], [p, first, second])
        self.assertNotIn(n1, log.ancestors[n2])
        self.assertEqual(log.ancestors[b.tip], frozenset(range(1, b.tip)))
        self.assertEqual(log.findings, [])                                           # a merge that adds nothing is clean

    def test_missing_branch_is_an_error_not_an_empty_state(self):
        b = story()
        repo = self.repo(b)
        with self.assertRaises((fixture.GitError, gitlog.LogError)):
            gitlog.read(repo, "no-such-branch")

    def test_what_a_commit_must_not_change(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        a = b.ack("bruno", p)
        b.tamper("ines", "header", {"kind": "field", "value": "Another title"})
        b.tamper("ines", "agent:bruno", {"kind": "field", "value": "visitor"})
        b.tamper("ines", a, {"kind": "delete"})
        log = gitlog.read(self.repo(b))
        self.assertEqual([(f.cls, f.commit_index, f.target) for f in log.findings],
                         [("V01", 4, "header"), ("V01", 5, "agent:bruno"), ("V01", 6, a)])
        self.assertEqual([e.id for e in log.entries], [p, a])                        # the removed entry is still in the log

    def test_two_entries_in_one_commit_are_read_top_to_bottom(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        stream = render.stream(b.events)
        log = gitlog.read(fixture.build_repo(stream, self.tmp / "plain.git"))
        self.assertEqual([(e.id, e.seq) for e in log.entries], [(p, 1), ("bruno-1", 1)])


if __name__ == "__main__":
    unittest.main()
