"""Profile-level Chinese/Russian name evidence.

Pairwise maxima are useful for recovering aliases, but a single accidental
match can also create a false link.  This module summarizes support and
contradiction across every distinct, source-observed structured name in an
author profile.  It never reads identity labels and never turns a dictionary
match into a hard merge.
"""

from __future__ import annotations

import math
from typing import Sequence

from disambiguation_engine.multilingual_name_features import (
    StructuredName,
    multilingual_name_features,
)
from disambiguation_engine.ruzh_name_evidence import ruzh_pair_features


FEATURE_NAMES = (
    "profile_name_view_log_count",
    "profile_name_support_mean",
    "profile_name_support_rate_085",
    "profile_name_conflict_rate",
    "profile_cross_script_support_rate",
    "profile_name_consensus_margin",
)


def profile_consensus_features(
    query: StructuredName,
    profile_names: Sequence[StructuredName],
) -> tuple[float, ...]:
    """Aggregate compatible and contradictory name evidence in O(V).

    ``V`` is the number of distinct structured name views in the candidate
    profile.  A compatible view needs both family-name and given-name support;
    an explicit conflict is emitted only by the traceable Chinese/Russian
    lexicons.
    """

    if not profile_names:
        return (0.0,) * len(FEATURE_NAMES)

    supports: list[float] = []
    conflicts: list[float] = []
    cross_script_supports: list[float] = []
    for profile_name in profile_names:
        multilingual = multilingual_name_features(query, profile_name)
        ruzh = ruzh_pair_features(
            query.first,
            query.middle,
            query.last,
            profile_name.first,
            profile_name.middle,
            profile_name.last,
        )
        family_support = max(
            multilingual[0],
            multilingual[2],
            multilingual[4],
        )
        given_support = max(
            multilingual[1],
            multilingual[3],
            multilingual[5],
            multilingual[6],
        )
        support = min(family_support, given_support)
        conflict = max(ruzh[3], ruzh[6])
        supports.append(support)
        conflicts.append(conflict)
        cross_script_supports.append(multilingual[12] * support)

    count = len(supports)
    support_mean = sum(supports) / count
    conflict_rate = sum(conflicts) / count
    features = (
        math.log1p(count),
        support_mean,
        sum(value >= 0.85 for value in supports) / count,
        conflict_rate,
        sum(cross_script_supports) / count,
        support_mean - conflict_rate,
    )
    if len(features) != len(FEATURE_NAMES):
        raise AssertionError("RuZh profile consensus feature schema mismatch")
    return features


__all__ = ["FEATURE_NAMES", "profile_consensus_features"]
