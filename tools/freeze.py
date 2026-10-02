"""Freeze the code the blind run will use.

    python tools/freeze.py            # write eval/FREEZE.sha256
    python tools/freeze.py --check    # compare the code on disk with it

The list is made by `eval/score.py` (`FROZEN_PATHS`): the tooling, the generator and the reference
reducer, the rule files, the schemas, the scorer and PROTOCOL.md. The blind suite refuses to run when
any of them differs from this list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import score                  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write or check eval/FREEZE.sha256.")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        diff = score.check_frozen()
        print(f"freeze: {'FAILED - ' + '; '.join(diff[:10]) if diff else 'OK - the code is the frozen one'}")
        return 1 if diff else 0
    files = score.frozen_files()
    with open(ROOT / "eval" / "FREEZE.sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(f"{sha}  {path}\n" for path, sha in sorted(files.items())))
    print(f"freeze: wrote {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
