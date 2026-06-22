"""Read-only GitHub PR review-comment source (PyGithub).

Least privilege: a token with *Pull requests: Read* + *Contents: Read* is enough.
This module never writes to GitHub. Comment bodies are redacted of obvious
secrets at fetch time, so nothing sensitive ever reaches the cache or DNA file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone


@dataclass
class ReviewComment:
    """One PR review comment, normalized across REST shapes."""

    body: str
    path: str
    pr_number: int
    author: str
    created_at: str
    # Approximate "addressed" signal: the comment's hunk no longer exists in the
    # current diff (position is None) or the PR merged. See note in ``_resolved``.
    addressed: bool

    def to_dict(self) -> dict:
        return asdict(self)


# Patterns for redaction. Conservative: aims to catch common token shapes without
# mangling ordinary prose.
_SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[oprsu]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # Bearer / Authorization values.
    re.compile(r"(?i)(authorization|bearer|api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
]


def redact(text: str) -> str:
    """Replace anything that looks like a secret with ``[REDACTED]``."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def parse_since(value: str | None) -> datetime | None:
    """Parse ``"90d"``/``"12w"``/``"6mo"`` or an ISO date into an aware datetime."""
    if not value:
        return None
    value = value.strip().lower()
    m = re.fullmatch(r"(\d+)\s*(d|w|mo|m|y)", value)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = {"d": 1, "w": 7, "mo": 30, "m": 30, "y": 365}[unit]
        return datetime.now(timezone.utc) - timedelta(days=n * days)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Could not parse --since value: {value!r}") from exc


def _resolved(comment, pr) -> bool:
    # PyGithub's review comments don't expose the GraphQL "resolved" flag, so we
    # approximate: an outdated comment (position is None -> its hunk changed) or a
    # merged PR implies the feedback was acted on. This is a heuristic signal used
    # only to weight clusters, never a hard filter.
    if getattr(comment, "position", None) is None:
        return True
    return bool(getattr(pr, "merged", False))


def fetch_review_comments(
    repo: str,
    *,
    since: str | None = None,
    limit: int = 50,
    token: str | None = None,
    api_url: str | None = None,
) -> list[ReviewComment]:
    """Fetch review comments from up to ``limit`` recently-updated PRs in ``repo``.

    ``repo`` is ``owner/name``. ``since`` bounds PRs by last-updated time. Requires
    a read-only token (``token`` arg or ``GITHUB_TOKEN`` env).
    """
    try:
        from github import Auth, Github  # PyGithub
    except ImportError as exc:  # pragma: no cover - dependency guidance
        raise RuntimeError(
            "PyGithub is required for mining. Install with: pip install PyGithub"
        ) from exc

    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "No GitHub token. Set GITHUB_TOKEN (read-only) or pass --token. "
            "See .env.example for least-privilege scopes."
        )

    api_url = api_url or os.environ.get("GITHUB_API_URL")
    auth = Auth.Token(token)
    gh = Github(auth=auth, base_url=api_url) if api_url else Github(auth=auth)

    cutoff = parse_since(since)
    out: list[ReviewComment] = []

    gh_repo = gh.get_repo(repo)
    pulls = gh_repo.get_pulls(state="all", sort="updated", direction="desc")

    scanned = 0
    for pr in pulls:
        if scanned >= limit:
            break
        updated = pr.updated_at
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if cutoff is not None and updated is not None and updated < cutoff:
            break  # list is sorted by updated desc, so we can stop
        scanned += 1

        for c in pr.get_review_comments():
            body = redact((c.body or "").strip())
            if not body:
                continue
            created = c.created_at
            out.append(
                ReviewComment(
                    body=body,
                    path=c.path or "",
                    pr_number=pr.number,
                    author=(c.user.login if c.user else ""),
                    created_at=created.isoformat() if created else "",
                    addressed=_resolved(c, pr),
                )
            )

    gh.close()
    return out
