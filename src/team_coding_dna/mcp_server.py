"""The Team Coding DNA MCP server (FastMCP).

This server **runs no LLM of its own** — it exposes the team's DNA as a resource
and three tools, and the developer's own AI client does all the reasoning. Every
byte returned is spent from the client's context budget, so responses are scoped,
capped, progressively-disclosed and terse (see :mod:`team_coding_dna.retrieval`).

Run it with ``dna serve`` (stdio). Point any MCP-aware client at that command.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import DEFAULT_MEMORY_FILE, load_env, memory, retrieval

mcp = FastMCP("team-coding-dna")

# Per-session cache so repeated get_relevant_rules calls in one session don't
# re-spend work (the results are tiny, but this keeps behaviour deterministic).
_RELEVANT_CACHE: dict[str, str] = {}


def _memory_path() -> Path:
    return Path(os.environ.get("DNA_MEMORY_FILE", DEFAULT_MEMORY_FILE))


# Cache parsed rules keyed by file mtime so edits are picked up without a restart.
_rules_cache: tuple[float, list] | None = None


def _load_rules() -> list:
    global _rules_cache
    path = _memory_path()
    if not path.exists():
        return []
    mtime = path.stat().st_mtime
    if _rules_cache is None or _rules_cache[0] != mtime:
        _rules_cache = (mtime, memory.parse(path))
    return _rules_cache[1]


def _terse(payload) -> str:
    """Compact JSON — no whitespace — to minimise tokens."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@mcp.resource(
    "dna://git_comment_memory.md",
    name="git_comment_memory.md",
    mime_type="text/markdown",
    description="The full Team Coding DNA file. Fetch on demand; do not auto-load.",
)
def memory_resource() -> str:
    """Return the full canonical DNA file (on-demand, never auto-loaded)."""
    path = _memory_path()
    return path.read_text(encoding="utf-8") if path.exists() else "# No DNA file yet. Run `dna init` or `dna distill`.\n"


@mcp.tool(
    description=(
        "Return the team's review rules that apply to a code change, as compact "
        "JSON [{id, rule, confidence}], ranked and capped. Call this BEFORE writing "
        "or reviewing code. Pass the unified diff (or the paths/languages you are "
        "about to touch). Use get_rule_detail(id) only when you need the full "
        "rationale or example for a specific rule."
    )
)
def get_relevant_rules(
    diff: str = "",
    languages: list[str] | None = None,
    paths: list[str] | None = None,
    category: str | None = None,
) -> str:
    """Scoped, ranked, capped (<=8) rules for this change. Terse by design."""
    key = hashlib.sha256(
        _terse([diff, languages or [], paths or [], category or ""]).encode("utf-8")
    ).hexdigest()
    if key in _RELEVANT_CACHE:
        return _RELEVANT_CACHE[key]

    rules = _load_rules()
    selected = retrieval.select_relevant(
        rules, diff, languages=languages, paths=paths, category=category
    )
    result = _terse(selected)
    _RELEVANT_CACHE[key] = result
    return result


@mcp.tool(
    description=(
        "Fetch the full detail (rationale, example, precedent PR, paths, languages) "
        "for ONE rule id, e.g. 'RULE-001'. Only call after get_relevant_rules."
    )
)
def get_rule_detail(id: str) -> str:
    """Full detail for a single rule id, or an error object if not found."""
    for rule in _load_rules():
        if rule.id == id:
            return _terse(retrieval.detail(rule))
    return _terse({"error": "not_found", "id": id})


def _mine_live(repo: str, since: str | None, limit: int | None) -> dict:
    """Fetch + cluster live from GitHub and refresh the local cache. Raises on error."""
    from .mining.cluster import cluster_comments
    from .mining.github_source import fetch_review_comments

    token = os.environ.get("GITHUB_TOKEN")
    comments = fetch_review_comments(repo, since=since or "90d", limit=limit or 50, token=token)
    clusters = cluster_comments(comments)
    payload = [cl.to_dict() for cl in clusters]

    # Refresh the same cache `dna mine` writes, so `dna distill` can reuse it.
    try:
        cache_dir = Path(".dna")
        cache_dir.mkdir(exist_ok=True)
        (cache_dir / "comments.json").write_text(
            _terse({"repo": repo, "comments": [c.to_dict() for c in comments]}),
            encoding="utf-8",
        )
        (cache_dir / "clusters.json").write_text(_terse(payload), encoding="utf-8")
    except OSError:
        pass  # caching is best-effort; the live result is still returned

    return {"clusters": payload, "source": "live", "repo": repo}


@mcp.tool(
    description=(
        "Mine recurring PR review comments and return them grouped into clusters, so "
        "YOUR model can summarise each into a rule — this server runs no model. If a "
        "GitHub token is available (GITHUB_TOKEN env or a local .env) it fetches live "
        "from the repo; otherwise it returns the cached result from `dna mine`, or "
        "guidance if neither exists. `repo` is 'owner/name' (auto-detected from the "
        "git remote when omitted)."
    )
)
def mine(repo: str | None = None, since: str | None = None, limit: int | None = None) -> str:
    """Live-fetch clusters when a token is present, else fall back to cache/guidance."""
    cache = Path(".dna") / "clusters.json"

    if not repo:
        try:
            from .mining import git_source

            repo = git_source.current_repo_slug()
        except Exception:  # noqa: BLE001 - detection is best-effort
            repo = None

    # 1) Live fetch when we have both a repo and a token.
    live_error = ""
    if repo and os.environ.get("GITHUB_TOKEN"):
        try:
            return _terse(_mine_live(repo, since, limit))
        except Exception as exc:  # noqa: BLE001 - network/auth/repo -> degrade gracefully
            live_error = str(exc)

    # 2) Fall back to the cache written by a prior `dna mine`.
    if cache.exists():
        clusters = json.loads(cache.read_text(encoding="utf-8"))
        return _terse({"clusters": clusters, "source": "cache"})

    # 3) Nothing available — explain exactly what to do.
    result = {
        "clusters": [],
        "hint": "No clusters available. Set GITHUB_TOKEN (or add it to a .env file) and "
        "ensure this repo has a github remote, then call mine again; or run "
        "`dna mine --repo owner/name --since 90d` on the CLI. Summarise each returned "
        "cluster into one rule and add it to git_comment_memory.md.",
    }
    if live_error:
        result["error"] = live_error
    return _terse(result)


def run() -> None:
    """Entry point used by ``dna serve``."""
    load_env()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
