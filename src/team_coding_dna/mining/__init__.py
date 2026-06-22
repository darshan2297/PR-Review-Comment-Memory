"""Language-agnostic mining: read git history + GitHub PR review comments and
group the recurring feedback into clusters ready for distillation.

The MCP server bundles no model; these modules only *fetch and group*. Turning
clusters into rules is done by the client's AI (via the ``mine`` tool) or an
optional headless model (``distill --model ...``).
"""
