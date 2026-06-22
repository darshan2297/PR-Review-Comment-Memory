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
