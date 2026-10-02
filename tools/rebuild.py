"""Rebuild every output of the pack into a folder and print one hash for the lot.

    python tools/rebuild.py --out DIR [--n 120]

What is rebuilt: the dev corpus (seed 20260930, standard profile), the state, status and lint report of
every story derived from its git history, the dev score, and the outputs of the ten scenarios. Run it
twice, in two different folders: the two `bundle sha256` lines must be identical.

Outputs cite commits by index, never by hash, so the bundle does not depend on commit hashes. The hashes
of the head commits of the test repositories are written apart (`head_commits.json`, with their own
digest) so that two machines can compare them; they are not part of the bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coord import fixture, gitlog, lint, state as state_mod, status        # noqa: E402
from coord.rules import load as load_rules                                 # noqa: E402
from corpus import generate                                                # noqa: E402
from eval import score                                                     # noqa: E402

BUNDLED = ("corpus", "states", "scenarios", "results_dev.json", "scenarios.json")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(out: Path) -> tuple[str, list[str]]:
    lines = []
    for name in BUNDLED:
        p = out / name
        files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file())
        for f in files:
            rel = f.relative_to(out).as_posix()
            if ".git/" in rel:                       # the test repositories themselves are not outputs
                continue
            lines.append(f"{sha(f)}  {rel}")
    lines.sort(key=lambda line: line.split("  ", 1)[1])
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest(), lines


def rebuild(out: Path, n: int) -> dict:
    fixture.rmtree(out)
    out.mkdir(parents=True)
    rules = load_rules()
    seed = generate.AUTHOR_SEEDS["dev"]
    index = generate.generate(seed, out / "corpus", "standard", n)
    heads = {}
    for row in index["stories"]:
        sid = row["id"]
        repo = fixture.build_repo((out / "corpus" / sid / "stream.fi").read_bytes(), out / "_work" / f"{sid}.git")
        log = gitlog.read(repo)
        st = state_mod.derive(log, rules)
        heads[sid] = st.head_sha
        write(out / "states" / f"{sid}.state.json", st.to_json())
        write(out / "states" / f"{sid}.status.txt", status.render(status.summary(st)))
        write(out / "states" / f"{sid}.lint.txt", lint.report(st))
        fixture.rmtree(repo)
    res = {"suite": "dev", **score.score_corpus(out / "corpus", out / "_work", index)}
    write(out / "results_dev.json", json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False))
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    cp = subprocess.run([sys.executable, str(ROOT / "scenarios" / "run_all.py"), "--work", str(out / "scenarios"),
                         "--json", str(out / "scenarios.json")], cwd=str(ROOT), env=env, capture_output=True)
    scen = json.loads((out / "scenarios.json").read_text(encoding="utf-8"))
    fixture.rmtree(out / "_work")
    digest, lines = bundle(out)
    write(out / "BUNDLE.sha256", "\n".join(lines))
    write(out / "head_commits.json", json.dumps(heads, indent=1, sort_keys=True))
    return {"bundle_sha256": digest, "files": len(lines), "corpus_sha256": generate.digest(index), "stories": len(index["stories"]),
            "seed": seed, "summary": score.summary(res), "scenarios": scen["result"], "scenarios_exit": cp.returncode,
            "head_commits_sha256": sha(out / "head_commits.json")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild every output of the pack and hash the lot.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=generate.DEFAULT_N, help="stories in the dev corpus (default: 120)")
    a = ap.parse_args(argv)
    r = rebuild(Path(a.out).resolve(), a.n)
    print(r["summary"])
    print(r["scenarios"])
    print(f"corpus sha256={r['corpus_sha256']} seed={r['seed']} stories={r['stories']}")
    print(f"head commits of the test repositories sha256={r['head_commits_sha256']} (not part of the bundle)")
    print(f"bundle sha256={r['bundle_sha256']} files={r['files']}")
    return 0 if r["scenarios_exit"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
