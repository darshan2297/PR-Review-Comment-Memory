"""Team Coding DNA — mine PR review history into a versioned DNA file and serve
it to any AI coding tool via an LLM-less MCP server.

The package is intentionally split so each concern is independently testable:

- ``memory``     parse/serialize the canonical ``git_comment_memory.md`` file.
- ``retrieval``  token-optimized, in-memory scope/rank/cap over the parsed rules.
- ``mining``     language-agnostic git + GitHub sources and vector-less clustering.
- ``distill``    turn raw comment clusters into rules (optional headless model).
- ``mcp_server`` the FastMCP server (runs no LLM of its own).
- ``cli``        the ``dna`` command (init / mine / distill / serve).
"""

__version__ = "0.1.0"

DEFAULT_MEMORY_FILE = "git_comment_memory.md"


def load_env() -> None:
    """Best-effort load of a local ``.env`` so ``GITHUB_TOKEN`` / ``DNA_MODEL`` just work.

    Searches the current working directory and its parents for a ``.env`` file and
    loads it without overriding variables already set in the real environment. A
    no-op if ``python-dotenv`` is unavailable or no ``.env`` exists, so it never
    fails a command. Call this at process entry points (CLI and the MCP server).
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)
