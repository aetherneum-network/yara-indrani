"""Shared by the tests: build a test repository from a story and read it back."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import ROOT

from coord import fixture, gitlog, rules as rules_mod, state as state_mod
from corpus import render, world
from corpus.events import StoryBuilder
from corpus.reference_reducer import reduce_events

RULES = rules_mod.load()
START = "2026-02-02T08:00:00Z"


def story(ids=("ines", "bruno", "carla", "dario"), company: str = "portoluna", start: str = START) -> StoryBuilder:
    team, agents = world.team(company, list(ids))
    return StoryBuilder(team, agents, start)


def child_env() -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    return env


def run(args: list[str], cwd: Path | str = ROOT, timeout: int = 170, extra_env: dict | None = None) -> tuple[int, str]:
    """Run `python <args>` in a minimal environment. Returns (exit code, stdout + stderr)."""
    env = child_env()
    env.update(extra_env or {})
    cp = subprocess.run([sys.executable, *map(str, args)], cwd=str(cwd), env=env, capture_output=True, timeout=timeout)
    return cp.returncode, (cp.stdout + cp.stderr).decode("utf-8", "replace").replace("\r\n", "\n")


class RepoCase(unittest.TestCase):
    """A test case with a temporary folder and helpers to turn events into a repository, a log and a state."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="coordpack-"))
        cls._count = 0

    @classmethod
    def tearDownClass(cls):
        fixture.rmtree(cls.tmp)

    def repo(self, events) -> Path:
        events = getattr(events, "events", events)
        type(self)._count += 1
        return fixture.build_repo(render.stream(events), self.tmp / f"r{self._count}.git")

    def derive(self, events, rules=None):
        log = gitlog.read(self.repo(events))
        return log, state_mod.derive(log, rules or RULES)

    def state(self, events, rules=None):
        return self.derive(events, rules)[1]

    def assert_gold(self, events, st=None):
        """The tool and the independent reference reducer agree on this story."""
        events = getattr(events, "events", events)
        st = st or self.state(events)
        gold = reduce_events(events)
        tool = st.as_dict()
        self.assertEqual(tool["state"], gold["state"])
        self.assertEqual(tool["release_gate"], gold["release_gate"])
        self.assertEqual(tool["violations"], gold["violations"])
        return st

    def classes(self, st) -> list[str]:
        return [v["class"] for v in st.violations]

    def assert_never_asserted(self, st, kind: str, oid: str):
        """The never-event: `oid` must not be declared aligned, decided, unblocked or lifted."""
        self.assertNotIn(st.status[kind][oid], ("ALIGNED", "DECIDED", "REMOVED", "LIFTED"),
                         f"{oid} was asserted as {st.status[kind][oid]} without the required consents")
