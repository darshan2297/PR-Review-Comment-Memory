"""Tests for compiling the DNA into per-tool instruction files + the CI workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from team_coding_dna import adapters
from team_coding_dna.memory import Rule

RULES = [
    Rule(
        id="RULE-001",
        title="Money is always Decimal, never float",
        rationale="Represent monetary values with Decimal; float rounds wrong.",
        confidence=0.95,
        languages=["python"],
        path_globs=["billing/**", "payments/**"],
        category="correctness",
    ),
    Rule(
        id="RULE-002",
        title="Use the gateway wrapper",
        rationale="Route billing calls through billing.gateway.",
        confidence=0.80,
        languages=["python"],
        category="architecture",
    ),
]


def test_render_block_has_instruction_and_every_rule():
    block = adapters.render_block(RULES)
    assert "get_relevant_rules" in block  # the standing MCP instruction
    assert "git_comment_memory.md" in block  # the no-MCP fallback source
    for r in RULES:
        assert r.id in block
        assert r.rationale in block


def test_render_block_orders_by_confidence_desc():
    block = adapters.render_block(RULES)
    assert block.index("RULE-001") < block.index("RULE-002")  # 0.95 before 0.80


def test_resolve_targets_all_and_subset_and_unknown():
    assert adapters.resolve_targets("all") == ["claude", "agents", "copilot", "cursor"]
    assert adapters.resolve_targets("") == ["claude", "agents", "copilot", "cursor"]
    # Subset is returned in canonical TARGETS order regardless of input order.
    assert adapters.resolve_targets("cursor,claude") == ["claude", "cursor"]
    with pytest.raises(ValueError):
        adapters.resolve_targets("nope")


def test_upsert_is_idempotent_and_preserves_surrounding_text():
    original = "# My project notes\n\nHand-written guidance.\n"
    once = adapters.upsert_managed_block(original, "BODY-A")
    twice = adapters.upsert_managed_block(once, "BODY-A")
    assert once == twice  # idempotent
    assert "Hand-written guidance." in once  # human content preserved
    assert once.count(adapters.BEGIN) == 1  # exactly one managed block


def test_upsert_replaces_only_the_block_on_rebuild():
    text = adapters.upsert_managed_block("Top.\n", "OLD")
    rebuilt = adapters.upsert_managed_block(text, "NEW")
    assert "NEW" in rebuilt
    assert "OLD" not in rebuilt
    assert "Top." in rebuilt
    assert rebuilt.count(adapters.BEGIN) == 1


def test_compile_targets_writes_all_files_with_correct_shape(tmp_path: Path):
    keys = adapters.resolve_targets("all")
    written = adapters.compile_targets(RULES, keys, root=tmp_path)
    paths = {key: Path(p) for key, p in written}

    # Shared files carry a managed block; the Cursor file is owned wholesale.
    claude = paths["claude"].read_text(encoding="utf-8")
    assert adapters.BEGIN in claude and adapters.END in claude

    cursor = paths["cursor"].read_text(encoding="utf-8")
    assert cursor.startswith("---\n")
    assert "alwaysApply: true" in cursor
    assert "RULE-001" in cursor

    # Nested parent dirs are created.
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()
    assert (tmp_path / ".cursor" / "rules" / "team-coding-dna.mdc").exists()


def test_compile_preserves_existing_claude_md(tmp_path: Path):
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text("# CLAUDE.md\n\nMy own rules.\n", encoding="utf-8")
    adapters.compile_targets(RULES, ["claude"], root=tmp_path)
    out = claude_path.read_text(encoding="utf-8")
    assert "My own rules." in out
    assert "RULE-001" in out


@pytest.mark.parametrize(
    "cadence,cron",
    [("daily", "0 6 * * *"), ("weekly", "0 6 * * 1"), ("monthly", "0 6 1 * *")],
)
def test_ci_workflow_yaml_cadence(cadence: str, cron: str):
    yaml = adapters.ci_workflow_yaml(cadence)
    assert f'cron: "{cron}"' in yaml
    assert "dna mine" in yaml and "dna distill" in yaml and "dna compile" in yaml
    assert "create-pull-request" in yaml  # opens a PR, not a direct commit
    assert "workflow_dispatch" in yaml  # manual run available


def test_ci_workflow_rejects_unknown_cadence():
    with pytest.raises(ValueError):
        adapters.ci_workflow_yaml("hourly")
