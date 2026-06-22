from team_coding_dna.mining.cluster import cluster_comments
from team_coding_dna.mining.github_source import ReviewComment, redact


def _c(body, path="billing/x.py", addressed=True, pr=1):
    return ReviewComment(body=body, path=path, pr_number=pr, author="rev",
                         created_at="2026-01-01T00:00:00", addressed=addressed)


def test_recurring_comments_cluster_together():
    comments = [
        _c("Please use Decimal for money, not float", pr=1),
        _c("Use Decimal for monetary values instead of float", pr=2),
        _c("money should be Decimal not float here", pr=3),
        _c("rename this variable", path="web/a.ts", pr=4),  # one-off, dropped
    ]
    clusters = cluster_comments(comments, min_count=2)
    assert len(clusters) == 1
    assert clusters[0].count == 3
    assert "python" in clusters[0].languages


def test_addressed_rate_increases_score():
    addressed = cluster_comments([_c("use decimal money", pr=i) for i in range(3)], min_count=2)
    ignored = cluster_comments(
        [_c("use decimal money", addressed=False, pr=i) for i in range(3)], min_count=2
    )
    assert addressed[0].score > ignored[0].score


def test_redact_strips_secrets():
    assert "REDACTED" in redact("token: ghp_" + "a" * 30)
    assert "REDACTED" in redact("password=hunter2")
    assert redact("just normal review text") == "just normal review text"
