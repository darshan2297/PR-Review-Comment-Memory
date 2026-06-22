"""Turn raw comment clusters into :class:`~team_coding_dna.memory.Rule` objects.

Two paths, mirroring the spec's "LLM-less by default" stance:

- ``heuristic`` (default, no model): derive a title + rule text directly from each
  cluster's representative comment. Good enough to bootstrap and fully offline.
- ``llm`` (optional, CI only): call the team's *own* headless model (Ollama or an
  OpenAI-compatible endpoint) to phrase a crisp rule. Never a bundled third party.

In interactive use the recommended path is neither of these on the server side —
the client's AI calls the ``mine`` MCP tool, reads the clusters, and writes the
rules itself, so no model runs in this process at all.
"""

from __future__ import annotations

import json
import os
import re

from .memory import Rule, next_rule_id
from .mining.cluster import Cluster
from .mining.github_source import redact

_MAX_TITLE = 72


def _confidence(cluster: Cluster) -> float:
    """Map recurrence + acted-on rate to a confidence in ``[0.5, 0.95]``."""
    rate = cluster.addressed_count / cluster.count if cluster.count else 0.0
    base = 0.5 + 0.06 * (cluster.count - 1) + 0.15 * rate
    return round(max(0.5, min(0.95, base)), 2)


def _clean(text: str) -> str:
    text = redact(text or "").strip()
    # Collapse whitespace and strip simple Markdown emphasis/code fences.
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip("`* \t")
    return text


def _title_from(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0].strip()
    if len(first) > _MAX_TITLE:
        first = first[: _MAX_TITLE - 1].rstrip() + "…"
    return first or "Team convention"


def _heuristic_rule(cluster: Cluster, rule_id: str, generated: str) -> Rule:
    rep = _clean(cluster.representative())
    return Rule(
        id=rule_id,
        title=_title_from(rep),
        rationale=rep,
        confidence=_confidence(cluster),
        languages=cluster.languages,
        path_globs=cluster.paths,
        category="general",
        precedent=(f"#{cluster.precedent_prs[0]}" if cluster.precedent_prs else ""),
        mined_date=generated,
        example="",
    )


# --- optional headless model -------------------------------------------------

_PROMPT = (
    "You are distilling a team's recurring code-review feedback into ONE rule.\n"
    "Given these near-duplicate review comments, output strict JSON with keys "
    '"title" (<= 10 words, imperative) and "rule" (one sentence, the convention). '
    "Capture the team-specific convention, not generic advice.\n\nComments:\n{body}"
)


def _call_model(prompt: str) -> str:
    """Call the team's own model. Spec: ``provider:model`` via env, OpenAI/Ollama."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("LLM distillation needs httpx: pip install 'team-coding-dna[llm]'") from exc

    spec = os.environ.get("DNA_MODEL", "")
    provider, _, model = spec.partition(":")
    base = os.environ.get("DNA_MODEL_BASE_URL", "")

    if provider == "ollama":
        base = base or "http://localhost:11434"
        r = httpx.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response", "")

    # OpenAI-compatible chat completions (the team's own key/endpoint).
    base = base or "https://api.openai.com/v1"
    key = os.environ.get("DNA_MODEL_API_KEY", "")
    r = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _llm_rule(cluster: Cluster, rule_id: str, generated: str) -> Rule:
    body = "\n".join(f"- {_clean(m.body)}" for m in cluster.members[:8])
    raw = _call_model(_PROMPT.format(body=body))
    title, rule = _title_from(_clean(cluster.representative())), _clean(cluster.representative())
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            title = (data.get("title") or title).strip()[:_MAX_TITLE]
            rule = (data.get("rule") or rule).strip()
        except json.JSONDecodeError:
            pass
    return Rule(
        id=rule_id,
        title=title,
        rationale=redact(rule),
        confidence=_confidence(cluster),
        languages=cluster.languages,
        path_globs=cluster.paths,
        category="general",
        precedent=(f"#{cluster.precedent_prs[0]}" if cluster.precedent_prs else ""),
        mined_date=generated,
    )


def distill(
    clusters: list[Cluster],
    existing: list[Rule],
    *,
    use_model: bool = False,
    generated: str = "",
) -> list[Rule]:
    """Produce new rules from clusters, assigning fresh ids after ``existing``.

    ``use_model=True`` uses the optional headless model (``DNA_MODEL`` env); on any
    model error it falls back to the heuristic for that cluster so mining never dies.
    """
    rules: list[Rule] = []
    pool = list(existing)
    for cl in clusters:
        rule_id = next_rule_id(pool + rules)
        if use_model:
            try:
                rule = _llm_rule(cl, rule_id, generated)
            except Exception:  # noqa: BLE001 - degrade gracefully to heuristic
                rule = _heuristic_rule(cl, rule_id, generated)
        else:
            rule = _heuristic_rule(cl, rule_id, generated)
        rules.append(rule)
    return rules
