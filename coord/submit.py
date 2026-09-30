"""Move the shared log forward - or say, in the first line, that it did not move.

    python -m coord.submit --repo <repository> --candidate <branch>

The shared log is the branch `main` of one local repository. A candidate (a branch holding one more
entry) is accepted only if `main` has not moved since the candidate was written: the same check a
server makes before accepting a push, done here on a local reference with compare-and-swap. There is no
remote and no network: this module never pushes, fetches or pulls.

After the write the reference is read again. "Sent" is only ever said about what that re-read shows; a
write that did not happen is a FAILED in the first line.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from coord import fixture

REF = "refs/heads/main"


def _rev(git_dir: Path, name: str) -> str | None:
    cp = fixture.git(["rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], git_dir=git_dir, check=False)
    return cp.stdout.decode().strip() or None if cp.returncode == 0 else None


def submit(repo: str | Path, candidate: str) -> tuple[bool, str]:
    """Try to make `candidate` the new tip of the shared log. Returns (accepted, one line saying what happened)."""
    git_dir = fixture.git_dir_of(repo)
    new = _rev(git_dir, f"refs/heads/{candidate}")
    old = _rev(git_dir, REF)
    if new is None:
        return False, f"submit: FAILED - there is no candidate '{candidate}'; nothing was written"
    if old is not None:
        seen = fixture.git(["merge-base", "--is-ancestor", old, new], git_dir=git_dir, check=False).returncode == 0
        if not seen:
            return False, (f"submit: FAILED - rejected: the shared log moved to {old[:12]} and '{candidate}' has not seen "
                           f"it; the entry is NOT in the shared log (merge, then submit again)")
    args = ["update-ref", REF, new] + ([old] if old is not None else [])
    moved = fixture.git(args, git_dir=git_dir, check=False)
    now = _rev(git_dir, REF)                       # read the state again before saying anything about it
    if moved.returncode != 0 or now != new:
        return False, f"submit: FAILED - the shared log is at {now[:12] if now else 'nothing'}, not at '{candidate}'"
    return True, f"submit: OK - the shared log is now at {new[:12]} (read back after the write)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coord.submit", description="Append a candidate to the shared log, or fail loudly.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--candidate", required=True, help="local branch holding the new entry")
    a = ap.parse_args(argv)
    try:
        ok, line = submit(a.repo, a.candidate)
    except fixture.GitError as exc:
        ok, line = False, f"submit: FAILED - {exc}"
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
