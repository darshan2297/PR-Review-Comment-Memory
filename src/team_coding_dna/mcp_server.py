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

from . import DEFAULT_MEMORY_FILE, memory, retrieval

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


@mcp.tool(
    description=(
        "Return grouped raw review comments (clusters) for interactive mining, so "
        "YOUR model can summarise them into rules — this server runs no model. Reads "
        "the local mining cache from `dna mine`; if none exists, returns guidance."
    )
)
def mine(repo: str | None = None, since: str | None = None, limit: int | None = None) -> str:
    """Return cached comment clusters for the client's model to distill."""
    cache = Path(".dna") / "clusters.json"
    if cache.exists():
        clusters = json.loads(cache.read_text(encoding="utf-8"))
        return _terse({"clusters": clusters, "source": "cache"})
    return _terse(
        {
            "clusters": [],
            "hint": "No mining cache. Run `dna mine --repo owner/name --since 90d` first, "
            "then call mine again. Summarise each cluster into one rule and add it to "
            "git_comment_memory.md (id, one-line rule, confidence, languages, paths).",
        }
    )


def run() -> None:
    """Entry point used by ``dna serve``."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
