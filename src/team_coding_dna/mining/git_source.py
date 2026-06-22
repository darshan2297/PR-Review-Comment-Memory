"""Thin, read-only wrappers over the local ``git`` CLI.

Used for repo auto-detection and local context. No assumptions about the repo's
languages are made here — mining is language-agnostic.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _run(args: list[str], cwd: str | Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:  # git not installed
        raise GitError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(exc.stderr.strip() or f"git {' '.join(args)} failed") from exc
    return result.stdout.strip()


def is_git_repo(cwd: str | Path | None = None) -> bool:
    try:
        return _run(["rev-parse", "--is-inside-work-tree"], cwd) == "true"
    except GitError:
        return False


# owner/name from a github remote URL (https or ssh form).
_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?$")


def current_repo_slug(cwd: str | Path | None = None) -> str | None:
    """Best-effort ``owner/name`` parsed from the ``origin`` remote URL."""
    try:
        url = _run(["remote", "get-url", "origin"], cwd)
    except GitError:
        return None
    m = _REMOTE_RE.search(url.strip())
    return f"{m.group('owner')}/{m.group('name')}" if m else None


def recent_commit_subjects(limit: int = 200, cwd: str | Path | None = None) -> list[str]:
    """Recent commit subject lines (local context for cold-start seeding)."""
    try:
        out = _run(["log", f"-n{limit}", "--pretty=format:%s"], cwd)
    except GitError:
        return []
    return [line for line in out.splitlines() if line.strip()]
