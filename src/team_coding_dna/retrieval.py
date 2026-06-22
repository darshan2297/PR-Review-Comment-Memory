"""Token-optimized, in-memory retrieval over parsed rules.

This module is the single place that enforces the spec's token-budget rules
(Section 6): every tool response should change the model's behaviour with the
least text possible. The retrieval is *vector-less* — deterministic full-text +
path/language filtering — so it is explainable and needs no vector infra.

Pipeline: ``scope`` (filter) → ``rank`` (confidence × relevance) → cap → ``dedup``
→ terse summaries (progressive disclosure: detail only via ``get_rule_detail``).
"""

from __future__ import annotations

import re
from .memory import Rule

DEFAULT_CAP = 8

# Map file extensions to coarse language names. Intentionally small and additive;
# mining is language-agnostic, this is only used to scope rules to a diff.
_EXT_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".tf": "terraform",
}

# Lines in a unified diff that reveal the file being changed.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+?)\s*$")
_DIFF_PLUS_RE = re.compile(r"^\+\+\+ b/(?P<path>.+?)\s*$")
_DIFF_MINUS_RE = re.compile(r"^--- a/(?P<path>.+?)\s*$")


def extract_changed_paths(diff: str) -> list[str]:
    """Pull the set of changed file paths out of a unified ``git diff``.

    Robust to diffs that include only ``+++``/``---`` headers (no ``diff --git``).
    Returns a de-duplicated, order-preserving list.
    """
    paths: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        p = p.strip()
        if not p or p == "/dev/null" or p in seen:
            return
        seen.add(p)
        paths.append(p)

    for line in (diff or "").splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            _add(m.group("b"))
            continue
        m = _DIFF_PLUS_RE.match(line)
        if m:
            _add(m.group("path"))
            continue
        m = _DIFF_MINUS_RE.match(line)
        if m:
            _add(m.group("path"))
    return paths


def detect_languages(paths: list[str]) -> set[str]:
    """Infer coarse languages from file extensions."""
    langs: set[str] = set()
    for p in paths:
        idx = p.rfind(".")
        if idx != -1:
            lang = _EXT_LANG.get(p[idx:].lower())
            if lang:
                langs.add(lang)
    return langs


def _glob_to_regex(glob: str) -> re.Pattern:
    """Translate a path glob to a regex. ``**`` spans directories, ``*`` does not."""
    out = ["^"]
    i = 0
    while i < len(glob):
        c = glob[i]
        if c == "*":
            if glob[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def path_matches(glob: str, path: str) -> bool:
    """True if ``path`` matches ``glob``. A bare ``name`` also matches as ``**/name``."""
    if _glob_to_regex(glob).match(path):
        return True
    # Convenience: "*.py" or "config.json" should match anywhere in the tree.
    if "/" not in glob:
        return _glob_to_regex(f"**/{glob}").match(path) is not None
    return False


def _rule_path_matches(rule: Rule, paths: list[str]) -> bool:
    return any(path_matches(g, p) for g in rule.path_globs for p in paths)


def scope(
    rules: list[Rule],
    paths: list[str],
    langs: set[str],
    category: str | None = None,
) -> list[Rule]:
    """Filter to rules that could apply to this change.

    A rule is in scope when its path globs match a changed path (or it has none)
    AND its languages overlap the changed languages (or it has none). Rules with
    neither constraint are global and always in scope. When the diff yields no
    paths/languages at all, scoping is skipped (ranking + cap still apply).
    """
    no_signal = not paths and not langs
    out: list[Rule] = []
    for r in rules:
        if category and r.category != category:
            continue
        if no_signal:
            out.append(r)
            continue
        path_ok = not r.path_globs or _rule_path_matches(r, paths)
        lang_ok = not r.languages or bool(set(r.languages) & langs)
        if path_ok and lang_ok:
            out.append(r)
    return out


def relevance(rule: Rule, paths: list[str], langs: set[str]) -> float:
    """Relevance of a rule to the change, in ``[0, 1]``."""
    score = 0.0
    if rule.path_globs and _rule_path_matches(rule, paths):
        score += 0.6
    if rule.languages and (set(rule.languages) & langs):
        score += 0.3
    if not rule.path_globs and not rule.languages:
        score += 0.2  # global baseline rule
    return max(score, 0.1)


def _normalize(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(tokens)


def dedup(rules: list[Rule]) -> list[Rule]:
    """Drop near-identical rules (Jaccard of rationale/title tokens > 0.8).

    Order is preserved; the first (higher-ranked) occurrence wins.
    """
    kept: list[Rule] = []
    kept_tokens: list[frozenset[str]] = []
    for r in rules:
        toks = _normalize(f"{r.title} {r.rationale}")
        is_dup = False
        for prev in kept_tokens:
            union = toks | prev
            if union and len(toks & prev) / len(union) > 0.8:
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
            kept_tokens.append(toks)
    return kept


def summary(rule: Rule) -> dict:
    """Terse default representation: id + one-line rule + confidence only."""
    return {
        "id": rule.id,
        "rule": rule.rationale or rule.title,
        "confidence": round(rule.confidence, 2),
    }


def detail(rule: Rule) -> dict:
    """Full representation, returned only by ``get_rule_detail``."""
    return {
        "id": rule.id,
        "title": rule.title,
        "rule": rule.rationale or rule.title,
        "confidence": round(rule.confidence, 2),
        "category": rule.category,
        "languages": rule.languages,
        "paths": rule.path_globs,
        "example": rule.example,
        "precedent": rule.precedent,
        "mined": rule.mined_date,
    }


def select_relevant(
    rules: list[Rule],
    diff: str = "",
    *,
    languages: list[str] | None = None,
    paths: list[str] | None = None,
    category: str | None = None,
    cap: int = DEFAULT_CAP,
) -> list[dict]:
    """End-to-end: scope → rank by confidence × relevance → cap → dedup → terse.

    ``languages`` / ``paths`` override what is inferred from ``diff`` (additive).
    Returns at most ``cap`` terse summaries — the minimum that changes behaviour.
    """
    changed_paths = list(paths or [])
    changed_paths += [p for p in extract_changed_paths(diff) if p not in changed_paths]

    langs = detect_languages(changed_paths)
    if languages:
        langs |= {l.lower() for l in languages}

    in_scope = scope(rules, changed_paths, langs, category=category)
    ranked = sorted(
        in_scope,
        key=lambda r: (r.confidence * relevance(r, changed_paths, langs), r.confidence),
        reverse=True,
    )
    deduped = dedup(ranked)
    return [summary(r) for r in deduped[:cap]]
