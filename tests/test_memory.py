from team_coding_dna import memory
from team_coding_dna.memory import Rule


def _sample_rules():
    return [
        Rule(
            id="RULE-001",
            title="Money is always Decimal, never float",
            rationale="Use Decimal for money; float rounds wrong.",
            confidence=0.95,
            languages=["python"],
            path_globs=["billing/**", "payments/**"],
            category="correctness",
            precedent="#1423",
            mined_date="2026-06-01",
            example='Decimal("19.99")',
        ),
        Rule(
            id="RULE-002",
            title="Use the retry util",
            rationale="Wrap outbound HTTP in retry().",
            confidence=0.8,
        ),
    ]


def test_round_trip_preserves_rules():
    rules = _sample_rules()
    reparsed = memory.parse_text(memory.serialize(rules))
    assert reparsed == sorted(rules, key=lambda r: r.numeric_id())


def test_parse_ignores_preamble():
    text = "# Title\n\nSome intro prose.\n\n## RULE-005: Do the thing\n- confidence: 0.7\n\n**Rule:** Do it.\n"
    rules = memory.parse_text(text)
    assert len(rules) == 1
    assert rules[0].id == "RULE-005"
    assert rules[0].confidence == 0.7
    assert rules[0].rationale == "Do it."


def test_confidence_is_clamped():
    text = "## RULE-009: x\n- confidence: 5\n\n**Rule:** y\n"
    assert memory.parse_text(text)[0].confidence == 1.0


def test_next_rule_id():
    assert memory.next_rule_id(_sample_rules()) == "RULE-003"
    assert memory.next_rule_id([]) == "RULE-001"


def test_merge_incoming_wins():
    existing = _sample_rules()
    incoming = [Rule(id="RULE-001", title="changed", confidence=0.1)]
    merged = memory.merge(existing, incoming)
    by_id = {r.id: r for r in merged}
    assert by_id["RULE-001"].title == "changed"
    assert len(merged) == 2
