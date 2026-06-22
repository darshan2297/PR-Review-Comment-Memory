# git_comment_memory.md

> Team Coding DNA — the team's review conventions, mined from PR history.
> This file is committed and versioned. Edit rules here or via `dna distill`.

_Source repo:_ `darshan2297/PR-Review-Comment-Memory`
_Last generated:_ 2026-06-22

## RULE-001: Money is always Decimal, never float
- confidence: 0.95
- languages: python
- paths: billing/**, payments/**
- category: correctness
- precedent: #1423
- mined: 2026-06-01

**Rule:** Represent monetary values with Decimal; float introduces rounding errors in billing.
**Example:** Decimal("19.99")  # not 19.99

## RULE-002: Don't call the billing API directly — use the gateway wrapper
- confidence: 0.90
- languages: python
- paths: billing/**, services/**
- category: architecture
- precedent: #1588
- mined: 2026-06-02

**Rule:** Route all billing calls through billing.gateway so retries, idempotency and audit logging are applied.
**Example:** gateway.charge(account, amount)  # not requests.post(BILLING_URL, ...)

## RULE-003: New endpoints must register with the rate-limiter
- confidence: 0.85
- languages: python, typescript
- paths: api/**, routes/**
- category: security
- precedent: #1601
- mined: 2026-06-03

**Rule:** Every new HTTP route registers with the shared rate-limiter; unthrottled endpoints are a DoS risk.
**Example:** @rate_limited(scope='public')

## RULE-004: Use our retry() util, not raw requests
- confidence: 0.80
- languages: python
- category: reliability
- precedent: #1490
- mined: 2026-06-04

**Rule:** Outbound HTTP goes through utils.retry() for consistent backoff and timeout handling.
**Example:** retry(lambda: client.get(url), attempts=3)
