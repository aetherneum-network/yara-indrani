"""Run the ten scenarios, one line each, then the total.

    python scenarios/run_all.py [--json reports/scenarios.json] [--work DIR] [--verbose]

Each scenario is run the way its `scenario.json` says, in its own folder, with a minimal environment:
no network is needed and nothing is installed. Exit code 0 only if every scenario passes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEP = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "PYTHONIOENCODING")


def scenario_dirs() -> list[Path]:
    return sorted(p.parent for p in HERE.glob("S*/scenario.json"))


def run_one(folder: Path, work: str | None) -> dict:
    spec = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    argv = [sys.executable if a in ("python", "python3") else a for a in spec["run"]]
    env = {k: v for k, v in os.environ.items() if k in KEEP}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    if work:
        env["COORD_PACK_WORK"] = work
    try:
        cp = subprocess.run(argv, cwd=str(folder), env=env, capture_output=True, timeout=spec.get("timeout_s", 60))
        code, out = cp.returncode, (cp.stdout + cp.stderr).decode("utf-8", "replace").replace("\r\n", "\n")
    except subprocess.TimeoutExpired:
        code, out = -1, f"{folder.name} FAIL (timeout after {spec.get('timeout_s', 60)} s)"
    last = [x for x in out.strip().split("\n") if x.strip()][-1:] or [f"{folder.name} FAIL (no output)"]
    passed = code == spec.get("expect_exit", 0)
    checks = [x.strip() for x in out.split("\n") if x.startswith("  ")]
    return {"scenario": folder.name, "passed": passed, "exit_code": code, "line": last[0],
            "checks": len([c for c in checks if c.startswith(("ok", "FAIL"))]),
            "failed_checks": [c for c in checks if c.startswith("FAIL")], "output": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the scenarios of the proof pack.")
    ap.add_argument("--json", help="write a machine-readable report (no timings, no hashes of commits)")
    ap.add_argument("--work", help="folder for the test repositories (default: build/scenarios)")
    ap.add_argument("--verbose", action="store_true", help="print every check, not only the result lines")
    a = ap.parse_args(argv)
    work = str(Path(a.work).resolve()) if a.work else None
    results = [run_one(d, work) for d in scenario_dirs()]
    for r in results:
        print(r["output"].rstrip() if a.verbose or not r["passed"] else r["line"])
    ok = sum(r["passed"] for r in results)
    total = f"scenarios: {ok}/{len(results)} PASS" + ("" if ok == len(results) else " - FAILED")
    print(total)
    if a.json:
        report = {"total": len(results), "passed": ok, "result": total,
                  "scenarios": [{k: r[k] for k in ("scenario", "passed", "exit_code", "checks", "failed_checks", "line")}
                                for r in results]}
        path = Path(a.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0 if ok == len(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
