"""Seed rules for ``dna init`` and cold-start.

These are *illustrative* team-DNA rules (the spec's examples) so a fresh clone has
a working DNA file and the MCP server returns something immediately. Replace them
with your own by running ``dna mine`` + ``dna distill`` against your PR history.
"""

from __future__ import annotations

from .memory import Rule

SEED_RULES: list[Rule] = [
    Rule(
        id="RULE-001",
        title="Money is always Decimal, never float",
        rationale="Represent monetary values with Decimal; float introduces rounding errors in billing.",
        confidence=0.95,
        languages=["python"],
        path_globs=["billing/**", "payments/**"],
        category="correctness",
        precedent="#1423",
        mined_date="2026-06-01",
        example='Decimal("19.99")  # not 19.99',
    ),
    Rule(
        id="RULE-002",
        title="Don't call the billing API directly — use the gateway wrapper",
        rationale="Route all billing calls through billing.gateway so retries, idempotency and audit logging are applied.",
        confidence=0.9,
        languages=["python"],
        path_globs=["billing/**", "services/**"],
        category="architecture",
        precedent="#1588",
        mined_date="2026-06-02",
        example="gateway.charge(account, amount)  # not requests.post(BILLING_URL, ...)",
    ),
    Rule(
        id="RULE-003",
        title="New endpoints must register with the rate-limiter",
        rationale="Every new HTTP route registers with the shared rate-limiter; unthrottled endpoints are a DoS risk.",
        confidence=0.85,
        languages=["python", "typescript"],
        path_globs=["api/**", "routes/**"],
        category="security",
        precedent="#1601",
        mined_date="2026-06-03",
        example="@rate_limited(scope='public')",
    ),
    Rule(
        id="RULE-004",
        title="Use our retry() util, not raw requests",
        rationale="Outbound HTTP goes through utils.retry() for consistent backoff and timeout handling.",
        confidence=0.8,
        languages=["python"],
        path_globs=[],
        category="reliability",
        precedent="#1490",
        mined_date="2026-06-04",
        example="retry(lambda: client.get(url), attempts=3)",
    ),
]
