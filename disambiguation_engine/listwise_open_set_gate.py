"""Interpretable open-set gate for graph-proposed author links.

The graph proposes an identity; this module decides whether the proposal is
safe enough to link.  Features deliberately describe only the proposal and
its candidate list.  Identity labels are used by the offline trainer only.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


FEATURE_NAMES = (
    "graph_support",
    "log_profile_size",
    "log_graph_candidate_count",
    "unique_graph_candidate",
    "log_paper_size",
    "fixed_merge_count",
    "proposal_in_topk",
    "proposal_score",
    "proposal_name_similarity",
    "proposal_coauthor_similarity",
    "proposal_is_top",
    "proposal_reciprocal_rank",
    "proposal_vs_best_other_margin",
    "top_score",
    "top_two_score_margin",
    "log_local_candidate_count",
    "base_unknown",
    "initial_heavy_name",
    "temporal_evidence_available",
    "log_years_since_latest_profile",
    "log_profile_year_span",
    "log_coauthor_overlap_count",
    "query_coauthor_containment",
    "profile_coauthor_containment",
    "candidate_score_entropy",
    "top_candidate_softmax_share",
)

BASE_FEATURE_COUNT = 18
FEATURE_GROUPS = {
    "graph_only": tuple(range(6)),
    "pointwise": tuple(range(11)),
    "listwise_no_cross_profile": tuple(range(BASE_FEATURE_COUNT)),
    "listwise": tuple(range(len(FEATURE_NAMES))),
}


def _initial_heavy(name: str) -> float:
    tokens = [token.strip(".,-()") for token in str(name or "").split()]
    tokens = [token for token in tokens if token]
    return float(
        bool(tokens)
        and sum(len(token) <= 2 for token in tokens) >= len(tokens) - 1
    )


def _normalized_values(values: Sequence[Any]) -> frozenset[str]:
    return frozenset(
        " ".join(str(value or "").casefold().split())
        for value in values
        if str(value or "").strip()
    )


def _score_distribution(scores: Sequence[float]) -> tuple[float, float]:
    """Return normalized entropy and the largest softmax share in O(C)."""

    if not scores:
        return 0.0, 0.0
    maximum = max(scores)
    weights = [math.exp(max(-50.0, score - maximum)) for score in scores]
    total = sum(weights)
    probabilities = [weight / total for weight in weights]
    if len(probabilities) == 1:
        return 0.0, 1.0
    entropy = -sum(
        probability * math.log(probability)
        for probability in probabilities
        if probability > 0.0
    ) / math.log(len(probabilities))
    return entropy, max(probabilities)


def graph_proposal_features(
    record: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    profile_size: int,
    paper_size: int,
    fixed_merge_count: int,
    query_year: int | None = None,
    profile_years: Sequence[int] = (),
    query_coauthors: Sequence[str] = (),
    profile_coauthors: Sequence[str] = (),
) -> tuple[float, ...]:
    """Return pointwise and listwise evidence without reading a gold label."""

    proposal_id = str(proposal.get("prediction") or "")
    candidates = list(record.get("topk") or [])
    selected_rank = next(
        (
            rank
            for rank, candidate in enumerate(candidates)
            if str(candidate.get("author_id") or "") == proposal_id
        ),
        None,
    )
    selected = candidates[selected_rank] if selected_rank is not None else {}
    components = selected.get("components") or {}
    comparisons = selected.get("comparisons") or {}
    scores = [float(candidate.get("score") or 0.0) for candidate in candidates]
    top_score = scores[0] if scores else 0.0
    second_score = scores[1] if len(scores) > 1 else top_score
    selected_score = float(selected.get("score") or 0.0)
    best_other = max(
        (
            float(candidate.get("score") or 0.0)
            for rank, candidate in enumerate(candidates)
            if rank != selected_rank
        ),
        default=selected_score,
    )
    valid_profile_years = []
    for year in profile_years:
        try:
            parsed_year = int(year)
        except (TypeError, ValueError):
            continue
        if parsed_year > 0:
            valid_profile_years.append(parsed_year)
    try:
        parsed_query_year = int(query_year or 0)
    except (TypeError, ValueError):
        parsed_query_year = 0
    temporal_available = bool(parsed_query_year > 0 and valid_profile_years)
    years_since_latest = (
        max(0, parsed_query_year - max(valid_profile_years))
        if temporal_available else 0
    )
    profile_year_span = (
        max(valid_profile_years) - min(valid_profile_years)
        if valid_profile_years else 0
    )
    query_coauthor_set = _normalized_values(query_coauthors)
    profile_coauthor_set = _normalized_values(profile_coauthors)
    coauthor_overlap = query_coauthor_set & profile_coauthor_set
    entropy, top_share = _score_distribution(scores)
    return (
        float(proposal.get("graph_support") or 0.0),
        math.log1p(max(0, int(profile_size))),
        math.log1p(max(0, int(proposal.get("candidate_count") or 0))),
        float(int(proposal.get("candidate_count") or 0) == 1),
        math.log1p(max(0, int(paper_size))),
        float(max(0, int(fixed_merge_count))),
        float(selected_rank is not None),
        selected_score,
        float(comparisons.get("name_sim") or components.get("name") or 0.0),
        float(comparisons.get("coauthor_sim") or components.get("coauthor") or 0.0),
        float(selected_rank == 0),
        1.0 / (float(selected_rank) + 1.0) if selected_rank is not None else 0.0,
        selected_score - best_other,
        top_score,
        top_score - second_score,
        math.log1p(max(0, int(record.get("candidate_count") or 0))),
        float(str(record.get("decision") or "") == "unknown"),
        _initial_heavy(str(record.get("name") or "")),
        float(temporal_available),
        math.log1p(years_since_latest),
        math.log1p(profile_year_span),
        math.log1p(len(coauthor_overlap)),
        (
            len(coauthor_overlap) / len(query_coauthor_set)
            if query_coauthor_set else 0.0
        ),
        (
            len(coauthor_overlap) / len(profile_coauthor_set)
            if profile_coauthor_set else 0.0
        ),
        entropy,
        top_share,
    )


def select_feature_group(
    features: Sequence[float],
    group: str,
) -> tuple[float, ...]:
    try:
        indices = FEATURE_GROUPS[group]
    except KeyError as exc:
        raise ValueError(f"unknown feature group: {group}") from exc
    if len(features) != len(FEATURE_NAMES):
        raise ValueError("listwise open-set feature count mismatch")
    return tuple(float(features[index]) for index in indices)


__all__ = [
    "BASE_FEATURE_COUNT",
    "FEATURE_GROUPS",
    "FEATURE_NAMES",
    "graph_proposal_features",
    "select_feature_group",
]
