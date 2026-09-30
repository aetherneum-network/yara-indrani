"""Test repositories with an isolated git configuration.

Every git call of this pack goes through `git()`: an explicit `--git-dir`, an environment built from
scratch (no user or system configuration, no credentials, no prompts) and only the local `file`
transport allowed. The pack never talks to a remote host.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

MIN_GIT = (2, 32)
_KEEP = ("PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "TMPDIR", "PATHEXT", "COMSPEC")


class GitError(RuntimeError):
    pass


def _empty_config() -> str:
    path = Path(tempfile.gettempdir()) / "coord-pack-empty.gitconfig"
    if not path.exists():
        path.write_bytes(b"")
    return str(path)


def git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _KEEP}
    cfg = _empty_config()
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": cfg, "GIT_CONFIG_GLOBAL": cfg,
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_ALLOW_PROTOCOL": "file",
        "GIT_PAGER": "cat", "PAGER": "cat", "LC_ALL": "C", "TZ": "UTC", "HOME": tempfile.gettempdir(),
    })
    return env


def git(args: list[str], *, git_dir: str | Path | None = None, stdin: bytes | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise GitError("git is not installed or not on PATH")
    cmd = [exe] + ([f"--git-dir={git_dir}"] if git_dir is not None else []) + list(args)
    cp = subprocess.run(cmd, input=stdin if stdin is not None else b"", capture_output=True, env=git_env())
    if check and cp.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])} failed ({cp.returncode}): {cp.stderr.decode('utf-8', 'replace').strip()}")
    return cp


def git_version() -> tuple[int, ...]:
    out = git(["--version"]).stdout.decode("ascii", "replace")
    nums = [int(x) for x in out.split()[2].split(".")[:3] if x.isdigit()]
    return tuple(nums)


def require_git() -> tuple[int, ...]:
    v = git_version()
    if v[:2] < MIN_GIT:
        raise GitError(f"git >= {MIN_GIT[0]}.{MIN_GIT[1]} is required, found {'.'.join(map(str, v))}")
    return v


def git_dir_of(path: str | Path) -> Path:
    """The git directory of a repository given its working tree or its bare directory."""
    p = Path(path)
    if (p / ".git").is_dir():
        return p / ".git"
    if (p / "HEAD").is_file() and (p / "objects").is_dir():
        return p
    raise GitError(f"{p.name} is not a git repository")


def rmtree(path: str | Path) -> None:
    """Remove a build directory (git marks object files read-only on Windows)."""
    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if Path(path).exists():
        shutil.rmtree(path, onexc=_retry)


def build_repo(stream: bytes, dest: str | Path) -> Path:
    """A fresh bare repository at `dest` holding the history described by a fast-import stream."""
    dest = Path(dest)
    rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    git(["init", "--quiet", "--bare", "--initial-branch=main", "--object-format=sha1", str(dest)])
    append_stream(stream, dest)
    return dest


def append_stream(stream: bytes, repo: str | Path) -> None:
    """Import more commits into an existing test repository."""
    git(["fast-import", "--quiet", "--date-format=raw"], git_dir=git_dir_of(repo), stdin=stream)


def head_sha(repo: str | Path, ref: str = "main") -> str:
    return git(["rev-parse", "--verify", f"refs/heads/{ref}^{{commit}}"], git_dir=git_dir_of(repo)).stdout.decode().strip()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build a test repository from a fast-import stream.")
    ap.add_argument("--stream", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    repo = build_repo(Path(a.stream).read_bytes(), a.out)
    print(f"built {repo.name}: head {head_sha(repo)}")
