"""Vector-less clustering of recurring review comments.

Deterministic and explainable: comments are normalized to token sets and grouped
greedily by Jaccard similarity. Clusters are scored by recurrence weighted by how
often the feedback was acted on (``addressed``) — frequent, acted-on feedback is
the strongest team-DNA signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .github_source import ReviewComment
from ..retrieval import detect_languages

# Words too generic to help group review comments.
_STOPWORDS = frozenset(
    """a an the this that these those is are be to of and or for in on at it its as
    we you i please can could should would need needs use using add added remove
    removed fix fixed change changed update updated make sure lets let s do not dont
    here there if then else than with without when while just also maybe think""".split()
)

_SIM_THRESHOLD = 0.5  # overlap coefficient at/above this joins a cluster.
_MIN_SHARED = 2       # ...and at least this many shared content tokens.


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", text.lower())
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 1)


def _similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap coefficient ``|a∩b| / min(|a|,|b|)``.

    More robust than Jaccard for short, length-varying review comments: a brief
    comment fully covered by a longer one still scores high. Guarded by a minimum
    shared-token count so a single common word can't merge unrelated comments.
    """
    if not a or not b:
        return 0.0
    shared = len(a & b)
    if shared < _MIN_SHARED:
        return 0.0
    return shared / min(len(a), len(b))


@dataclass
class Cluster:
    """A group of near-duplicate comments — a candidate team rule."""

    members: list[ReviewComment] = field(default_factory=list)
    _tokens: frozenset[str] = frozenset()

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def addressed_count(self) -> int:
        return sum(1 for m in self.members if m.addressed)

    @property
    def paths(self) -> list[str]:
        return sorted({m.path for m in self.members if m.path})

    @property
    def languages(self) -> list[str]:
        return sorted(detect_languages(self.paths))

    @property
    def precedent_prs(self) -> list[int]:
        return sorted({m.pr_number for m in self.members})

    @property
    def score(self) -> float:
        """Recurrence × (1 + acted-on rate). Higher = stronger DNA signal."""
        rate = self.addressed_count / self.count if self.count else 0.0
        return self.count * (1.0 + rate)

    def representative(self) -> str:
        """The longest member body — usually the most explanatory phrasing."""
        return max((m.body for m in self.members), key=len, default="")

    def to_dict(self, *, max_examples: int = 3) -> dict:
        examples = [m.body for m in self.members[:max_examples]]
        return {
            "representative": self.representative(),
            "count": self.count,
            "addressed_count": self.addressed_count,
            "score": round(self.score, 2),
            "paths": self.paths,
            "languages": self.languages,
            "precedent_prs": self.precedent_prs,
            "examples": examples,
        }


def cluster_comments(
    comments: list[ReviewComment],
    *,
    min_count: int = 2,
    threshold: float = _SIM_THRESHOLD,
) -> list[Cluster]:
    """Greedily group comments into clusters of recurring feedback.

    Only clusters seen at least ``min_count`` times are returned (a one-off comment
    is not yet team DNA). Results are sorted by descending score.
    """
    clusters: list[Cluster] = []
    for c in comments:
        toks = _tokens(c.body)
        if not toks:
            continue
        best: Cluster | None = None
        best_sim = threshold
        for cl in clusters:
            sim = _similarity(toks, cl._tokens)
            if sim >= best_sim:
                best, best_sim = cl, sim
        if best is None:
            clusters.append(Cluster(members=[c], _tokens=toks))
        else:
            best.members.append(c)
            # Centroid grows by union so related phrasings keep joining.
            best._tokens = best._tokens | toks

    recurring = [cl for cl in clusters if cl.count >= min_count]
    recurring.sort(key=lambda cl: cl.score, reverse=True)
    return recurring
