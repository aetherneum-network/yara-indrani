"""SHA-256 of every file of the pack.

    python tools/manifest.py            # write MANIFEST.sha256
    python tools/manifest.py --check    # compare the files on disk with MANIFEST.sha256

Text files are hashed with LF line endings, so the manifest is the same on every system. Build folders,
caches, results of later blind runs (`eval/blind/`) and the manifest itself are not listed.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "MANIFEST.sha256"
SKIP_DIRS = (".git", "build", "dist", "__pycache__", "corpus/out", "eval/blind", ".pytest_cache", ".idea", ".vscode")
BINARY = (".jpg", ".png", ".fi")


def listed() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if not p.is_file() or rel == NAME or rel.endswith(".pyc"):
            continue
        if any(rel == d or rel.startswith(d + "/") or f"/{d}/" in f"/{rel}" for d in SKIP_DIRS):
            continue
        out.append(p)
    return out


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix not in BINARY:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def lines() -> list[str]:
    return [f"{digest(p)}  {p.relative_to(ROOT).as_posix()}" for p in listed()]


def check() -> list[str]:
    path = ROOT / NAME
    if not path.is_file():
        return [f"{NAME} is missing"]
    want = dict(reversed(x.split("  ", 1)) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
    have = dict(reversed(x.split("  ", 1)) for x in lines())
    return [f"{p}: {'changed' if p in want and p in have else 'missing' if p in want else 'not in the manifest'}"
            for p in sorted(set(want) | set(have)) if want.get(p) != have.get(p)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write or check MANIFEST.sha256.")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        diff = check()
        print(f"manifest: {'FAILED - ' + '; '.join(diff[:10]) if diff else 'OK'}" + (f" (+{len(diff) - 10} more)" if len(diff) > 10 else ""))
        return 1 if diff else 0
    rows = lines()
    with open(ROOT / NAME, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    print(f"manifest: wrote {len(rows)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
