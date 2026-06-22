"""Canonical ``git_comment_memory.md`` model + parser/serializer.

The DNA file is committed to the repo, so it must stay human-reviewable *and*
machine-parseable. We use a small, deliberately simple Markdown convention: a
free-form preamble, then one ``## RULE-NNN: <title>`` section per rule, each with
a dashed metadata list and ``**Rule:**`` / ``**Example:**`` bodies.

The format is round-trippable at the rule level: ``parse(serialize(rules))``
yields rules equal to ``rules`` (see ``tests/test_memory.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

# A rule heading, e.g. "## RULE-007: Money is always Decimal, never float".
_HEADING_RE = re.compile(r"^##\s+(?P<id>RULE-\d+)\s*:\s*(?P<title>.+?)\s*$")
# A metadata bullet, e.g. "- confidence: 0.95".
_META_RE = re.compile(r"^-\s+(?P<key>[a-zA-Z_]+)\s*:\s*(?P<value>.*?)\s*$")
# A labelled body line, e.g. "**Rule:** Use Decimal ...".
_BODY_RE = re.compile(r"^\*\*(?P<label>Rule|Example|Rationale)\:\*\*\s*(?P<text>.*)$")

_LIST_FIELDS = {"languages", "paths"}


@dataclass
class Rule:
    """One distilled team convention.

    ``rationale`` is the short imperative rule shown in default tool responses;
    ``example`` and ``precedent`` are detail-only (progressive disclosure).
    """

    id: str
    title: str
    rationale: str = ""
    confidence: float = 0.5
    languages: list[str] = field(default_factory=list)
    path_globs: list[str] = field(default_factory=list)
    category: str = "general"
    precedent: str = ""
    mined_date: str = ""
    example: str = ""

    def numeric_id(self) -> int:
        """Integer portion of ``RULE-007`` -> ``7`` (0 if unparseable)."""
        m = re.search(r"(\d+)", self.id)
        return int(m.group(1)) if m else 0


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_text(text: str) -> list[Rule]:
    """Parse the DNA Markdown into a list of :class:`Rule`.

    Any preamble before the first ``## RULE-`` heading is ignored. Unknown
    metadata keys are ignored so the format can grow without breaking old files.
    """
    rules: list[Rule] = []
    current: dict | None = None

    def _flush() -> None:
        if current is None:
            return
        rules.append(
            Rule(
                id=current["id"],
                title=current["title"],
                rationale=current.get("rationale", "").strip(),
                confidence=_coerce_confidence(current.get("confidence")),
                languages=current.get("languages", []),
                path_globs=current.get("paths", []),
                category=current.get("category", "general") or "general",
                precedent=current.get("precedent", "") or "",
                mined_date=current.get("mined", "") or "",
                example=current.get("example", "").strip(),
            )
        )

    for raw in text.splitlines():
        line = raw.rstrip()

        heading = _HEADING_RE.match(line)
        if heading:
            _flush()
            current = {"id": heading.group("id"), "title": heading.group("title")}
            continue

        if current is None:
            continue  # still in preamble

        meta = _META_RE.match(line)
        if meta:
            key = meta.group("key").lower()
            value = meta.group("value")
            current[key] = _split_csv(value) if key in _LIST_FIELDS else value
            continue

        body = _BODY_RE.match(line)
        if body:
            label = body.group("label").lower()
            # "Rationale" is an accepted alias for "Rule".
            slot = "rationale" if label in ("rule", "rationale") else "example"
            current[slot] = (current.get(slot, "") + body.group("text")).strip()
            current["_last_body_slot"] = slot
            continue

        # Continuation line for the most recent body slot, if any.
        if line and current.get("_last_body_slot"):
            last = current["_last_body_slot"]
            current[last] = (current.get(last, "") + "\n" + line).strip()

    _flush()
    return rules


def _coerce_confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, c))


def parse(path: str | Path) -> list[Rule]:
    """Parse a DNA file from disk. Returns ``[]`` if the file does not exist."""
    p = Path(path)
    if not p.exists():
        return []
    return parse_text(p.read_text(encoding="utf-8"))


def serialize(rules: list[Rule], *, repo: str = "", generated: str = "") -> str:
    """Render rules to canonical DNA Markdown (stable ordering by numeric id)."""
    ordered = sorted(rules, key=lambda r: (r.numeric_id(), r.id))
    lines: list[str] = [
        "# git_comment_memory.md",
        "",
        "> Team Coding DNA — the team's review conventions, mined from PR history.",
        "> This file is committed and versioned. Edit rules here or via `dna distill`.",
        "",
    ]
    if repo:
        lines.append(f"_Source repo:_ `{repo}`")
    if generated:
        lines.append(f"_Last generated:_ {generated}")
    if repo or generated:
        lines.append("")

    for r in ordered:
        lines.append(f"## {r.id}: {r.title}")
        lines.append(f"- confidence: {r.confidence:.2f}")
        if r.languages:
            lines.append(f"- languages: {', '.join(r.languages)}")
        if r.path_globs:
            lines.append(f"- paths: {', '.join(r.path_globs)}")
        lines.append(f"- category: {r.category}")
        if r.precedent:
            lines.append(f"- precedent: {r.precedent}")
        if r.mined_date:
            lines.append(f"- mined: {r.mined_date}")
        lines.append("")
        if r.rationale:
            lines.append(f"**Rule:** {r.rationale}")
        if r.example:
            lines.append(f"**Example:** {r.example}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write(rules: list[Rule], path: str | Path, **kwargs) -> None:
    Path(path).write_text(serialize(rules, **kwargs), encoding="utf-8")


def next_rule_id(rules: list[Rule]) -> str:
    """Return the next free ``RULE-NNN`` id, zero-padded to 3 digits."""
    highest = max((r.numeric_id() for r in rules), default=0)
    return f"RULE-{highest + 1:03d}"


def merge(existing: list[Rule], incoming: list[Rule]) -> list[Rule]:
    """Merge ``incoming`` rules into ``existing`` by id (incoming wins)."""
    by_id = {r.id: r for r in existing}
    for r in incoming:
        by_id[r.id] = replace(r)
    return list(by_id.values())
