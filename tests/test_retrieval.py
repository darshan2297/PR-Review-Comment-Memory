from team_coding_dna import retrieval
from team_coding_dna.memory import Rule


def _rules(n_global=0, **_):
    rules = [
        Rule(id="RULE-001", title="Decimal money", rationale="Use Decimal for money",
             confidence=0.95, languages=["python"], path_globs=["billing/**"], category="correctness"),
        Rule(id="RULE-002", title="Rate limiter", rationale="Register endpoints with rate limiter",
             confidence=0.85, languages=["python"], path_globs=["api/**"], category="security"),
        Rule(id="RULE-003", title="TS strict", rationale="Enable strict mode",
             confidence=0.7, languages=["typescript"], path_globs=["web/**"]),
        Rule(id="RULE-004", title="Retry util", rationale="Use retry() for outbound http",
             confidence=0.8, category="reliability"),  # global rule
    ]
    return rules


def test_scopes_to_changed_paths():
    diff = "+++ b/billing/charge.py\n"
    out = retrieval.select_relevant(_rules(), diff)
    ids = [r["id"] for r in out]
    assert "RULE-001" in ids          # billing python rule applies
    assert "RULE-004" in ids          # global rule always applies
    assert "RULE-003" not in ids      # typescript/web rule does not


def test_ranks_specific_over_global():
    diff = "+++ b/billing/charge.py\n"
    out = retrieval.select_relevant(_rules(), diff)
    assert out[0]["id"] == "RULE-001"  # path+lang+high confidence ranks top


def test_cap_is_respected():
    many = [Rule(id=f"RULE-{i:03d}", title=f"r{i}", rationale=f"rule number {i}", confidence=0.9)
            for i in range(1, 30)]
    out = retrieval.select_relevant(many, "")
    assert len(out) <= retrieval.DEFAULT_CAP


def test_default_response_is_terse():
    out = retrieval.select_relevant(_rules(), "+++ b/billing/charge.py\n")
    for item in out:
        # progressive disclosure: no example/precedent/paths leaked by default
        assert set(item.keys()) == {"id", "rule", "confidence"}


def test_dedup_merges_near_identical():
    dup = [
        Rule(id="RULE-010", title="Use Decimal for money", rationale="Always use Decimal for monetary values", confidence=0.9),
        Rule(id="RULE-011", title="Use Decimal for money", rationale="Always use Decimal for monetary values", confidence=0.8),
    ]
    out = retrieval.select_relevant(dup, "")
    assert len(out) == 1
    assert out[0]["id"] == "RULE-010"  # higher confidence kept


def test_detail_includes_full_fields():
    rule = _rules()[0]
    d = retrieval.detail(rule)
    assert d["id"] == "RULE-001"
    assert "example" in d and "precedent" in d and "paths" in d
