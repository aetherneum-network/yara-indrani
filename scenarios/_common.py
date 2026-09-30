"""Shared by the ten scenario checks: build the test repository, compare, report.

A check never talks to a network and never installs anything. It builds a git repository from the
fast-import stream in `input/`, runs the tooling on it, and compares with `expected/`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coord import fixture, gitlog, rules as rules_mod, state as state_mod       # noqa: E402

_KEEP = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "PYTHONIOENCODING", "COORD_PACK_WORK")


def child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _KEEP}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class Scenario:
    def __init__(self, check_file: str):
        self.dir = Path(check_file).resolve().parent
        self.name = self.dir.name
        base = Path(os.environ["COORD_PACK_WORK"]) if os.environ.get("COORD_PACK_WORK") else ROOT / "build" / "scenarios"
        self.work = base / self.name
        fixture.rmtree(self.work)
        (self.work / "out").mkdir(parents=True)
        self.lines: list[str] = []
        self.failed = 0
        self.checks = 0

    # -- inputs and expectations --------------------------------------------------------------------------
    def input(self, name: str) -> Path:
        return self.dir / "input" / name

    def expected(self, name: str = "declared.json") -> dict:
        return json.loads((self.dir / "expected" / name).read_text(encoding="utf-8"))

    def repo(self, stream: str = "stream.fi", label: str = "repo") -> Path:
        return fixture.build_repo(self.input(stream).read_bytes(), self.work / f"{label}.git")

    def append(self, repo: Path, stream: str) -> None:
        fixture.append_stream(self.input(stream).read_bytes(), repo)

    def state(self, repo: Path, rules_dir: Path | None = None):
        log = gitlog.read(repo)
        return log, state_mod.derive(log, rules_mod.load(rules_dir))

    def cli(self, module: str, *args: str) -> tuple[int, str]:
        """Run one of the pack's commands the way a reader would; returns (exit code, output)."""
        cp = subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=str(ROOT), env=child_env(),
                            capture_output=True, timeout=60)
        return cp.returncode, (cp.stdout + cp.stderr).decode("utf-8", "replace").replace("\r\n", "\n")

    # -- checks ---------------------------------------------------------------------------------------------
    def eq(self, label: str, got, want) -> bool:
        self.checks += 1
        ok = got == want
        if not ok:
            self.failed += 1
            self.lines.append(f"  FAIL {label}\n       got  {json.dumps(got, ensure_ascii=False, sort_keys=True)[:400]}"
                              f"\n       want {json.dumps(want, ensure_ascii=False, sort_keys=True)[:400]}")
        else:
            self.lines.append(f"  ok   {label}")
        return ok

    def true(self, label: str, cond: bool, detail: str = "") -> bool:
        self.checks += 1
        if not cond:
            self.failed += 1
        self.lines.append(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"\n       {detail[:400]}" if detail and not cond else ""))
        return bool(cond)

    def subset(self, label: str, got: dict, want: dict) -> bool:
        """Every declared status is what the tooling says (the declaration may name only some objects)."""
        return self.eq(label, {k: got.get(k) for k in want}, want)

    def against_gold(self, st, gold: dict, label: str = "") -> bool:
        tool = st.as_dict()
        tag = f" ({label})" if label else ""
        ok = self.eq(f"status of every object = reference reducer{tag}", tool["state"], gold["state"])
        ok &= self.eq(f"release gate = reference reducer{tag}", tool["release_gate"], gold["release_gate"])
        ok &= self.eq(f"violations = reference reducer{tag}", tool["violations"], gold["violations"])
        key = lambda e: (e["block"], e["on"], e["refs"], e["active"])
        ok &= self.eq(f"dependency edges = reference reducer{tag}", sorted(map(key, tool["edges"])), sorted(map(key, gold["edges"])))
        return ok

    def write(self, name: str, text: str) -> None:
        with open(self.work / "out" / name, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")

    def finish(self) -> int:
        verdict = "FAIL" if self.failed else "PASS"
        out = "\n".join(self.lines + [f"{self.name} {verdict} ({self.checks - self.failed}/{self.checks} checks)"])
        sys.stdout.buffer.write((out + "\n").encode("utf-8"))
        return 1 if self.failed else 0
