"""Rank fusion and diversification: the pure arithmetic behind semantic search and answers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Hashable, Sequence

RRF_K = 60


def reciprocal_rank_fusion[K: Hashable](*rankings: Sequence[K], k: int = RRF_K) -> dict[K, float]:
    """Score each item by the sum of 1 / (k + rank) over the lists it appears in.

    Rank fusion needs no score calibration between a cosine similarity and a text rank,
    which is why it is the standard way to combine the two (Cormack et al., 2009).
    """
    scores: dict[K, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def cap_per_group[T](
    items: Sequence[T], group: Callable[[T], Hashable], per_group: int, limit: int
) -> list[T]:
    """The best items in order, at most `per_group` from each group (file), at most `limit`.

    Without a cap, one long file with many similar chunks crowds out every other file.
    """
    seen: Counter[Hashable] = Counter()
    kept: list[T] = []
    for item in items:
        key = group(item)
        if seen[key] >= per_group:
            continue
        seen[key] += 1
        kept.append(item)
        if len(kept) >= limit:
            break
    return kept
