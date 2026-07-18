"""Frozen interpretable candidate-risk model for the ISTINA runtime.

The coefficients were fitted on OpenAlex/ORCID-blind seed 20260719 and the
acceptance threshold was selected once on seed 20260720 under an unseen-author
false-link limit of 0.1%.  Runtime inference uses only Python's standard
library and the already-audited candidate comparison features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


MODEL_VERSION = "openalex-orcid-blind-logit-20260719-v1"
DEFAULT_ACCEPT_THRESHOLD = 0.9497593527686253

FEATURE_MEAN = (
    -3.610899498797079, 0.43849376097466886, -2.8907261555761754,
    2.418944850240238, 2.294341792101644, 0.9717870191947856,
    -1.5730597378623525, -1.526821322475204, -1.1463330497128865,
    -0.33647200000001154, 0.5746551258724957, 0.030344788545059866,
    0.023731968357375524, 0.1988872252598102, -0.880583164319791,
    -0.8897577525168221, 0.027976841891274452, 0.05308670699550178,
    0.12920738327904452, 0.16022956413835893, 0.2194431518535753,
    0.25356755079882115, 0.11074918566775244, 0.005855436637195595,
    0.0008143322475570033,
)
FEATURE_SCALE = (
    3.104501541246728, 0.3789630430676862, 3.527303436150046,
    3.293204160196788, 1.0626639582421296, 1.9290169575079232,
    0.840177768150916, 0.5298895800636941, 1.280987974354841, 1.0,
    0.24379533219269353, 0.13551300087555887, 0.1522128839331869,
    0.210914914912822, 3.7025338188193553, 4.239931229744594,
    0.12830169296566726, 0.22420639717877042, 0.3354293299417698,
    0.3668188257360025, 0.4138693694369814, 0.4350529254938743,
    0.3138212923650201, 0.07629646452477643, 0.028524885811286812,
)
COEFFICIENTS = (
    -3.0337620417951303, 0.25340334797583985, 0.7364127364628656,
    0.7176754910891995, -0.5952938508825186, -2.516171852221225,
    0.22316468643671752, 1.801596832034219, 0.07684402390442373,
    -0.9353598464111548, 0.0, 0.6911258324100588,
    0.9937300050010983, 0.07684402390444227, 0.5022859763395046,
    -0.4239424704365598, 1.134060675750144, 0.3244150145447923,
    -0.04172416785567916, 0.3232607106238459, 2.0763205978654176,
    0.5212984995511613, 0.12095267227176713, -0.5452642536966907,
    0.03494447085699278, 0.030278631100287015,
)


@dataclass(frozen=True)
class CalibratedCandidatePrediction:
    author_id: str
    probability: float
    rank: int


def _initial_heavy(name: str) -> float:
    tokens = [token.strip(".,-()") for token in str(name or "").split()]
    tokens = [token for token in tokens if token]
    return float(
        bool(tokens)
        and sum(len(token) <= 2 for token in tokens) >= len(tokens) - 1
    )


def candidate_features(
    mention_name: str,
    stage: str,
    candidate_count: int,
    candidates: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    rank: int,
) -> tuple[float, ...]:
    components = candidate.get("components") or {}
    comparisons = candidate.get("comparisons") or {}
    score = float(candidate.get("score") or 0.0)
    top_score = float(candidates[0].get("score") or 0.0)
    second_score = (
        float(candidates[1].get("score") or top_score)
        if len(candidates) > 1 else top_score
    )
    name = float(components.get("name") or 0.0)
    coauthor = float(components.get("coauthor") or 0.0)
    affiliation = float(components.get("affiliation") or 0.0)
    name_similarity = float(comparisons.get("name_sim") or 0.0)
    coauthor_similarity = float(comparisons.get("coauthor_sim") or 0.0)
    return (
        score,
        1.0 / (rank + 1.0),
        score - top_score,
        top_score - second_score,
        math.log1p(float(candidate_count)),
        name,
        coauthor,
        float(components.get("journal") or 0.0),
        affiliation,
        float(components.get("orcid") or 0.0),
        name_similarity,
        coauthor_similarity,
        float(comparisons.get("journal_sim") or 0.0),
        float(comparisons.get("affiliation_sim") or 0.0),
        name * coauthor,
        name * affiliation,
        name_similarity * coauthor_similarity,
        float(coauthor > 0.0),
        float(affiliation > 0.0),
        float(name >= 4.0),
        float(name >= 2.0),
        _initial_heavy(mention_name),
        float(stage == "dense_name_block_context_guard"),
        float(stage == "weak_name_context_guard"),
        float(stage == "enhanced_blocking_source_guard"),
    )


def predict_probability(features: Sequence[float]) -> float:
    if len(features) != len(FEATURE_MEAN):
        raise ValueError("calibrated candidate feature count mismatch")
    linear = COEFFICIENTS[0]
    for value, mean, scale, coefficient in zip(
        features,
        FEATURE_MEAN,
        FEATURE_SCALE,
        COEFFICIENTS[1:],
    ):
        linear += ((float(value) - mean) / scale) * coefficient
    linear = max(-35.0, min(35.0, linear))
    return 1.0 / (1.0 + math.exp(-linear))


def select_calibrated_candidate(
    mention_name: str,
    stage: str,
    candidate_count: int,
    candidates: Sequence[Mapping[str, Any]],
) -> CalibratedCandidatePrediction | None:
    predictions = []
    for rank, candidate in enumerate(candidates):
        author_id = str(candidate.get("author_id") or "")
        if not author_id:
            continue
        probability = predict_probability(candidate_features(
            mention_name,
            stage,
            candidate_count,
            candidates,
            candidate,
            rank,
        ))
        predictions.append(CalibratedCandidatePrediction(
            author_id=author_id,
            probability=probability,
            rank=rank,
        ))
    return max(predictions, key=lambda item: item.probability, default=None)


__all__ = [
    "CalibratedCandidatePrediction",
    "DEFAULT_ACCEPT_THRESHOLD",
    "MODEL_VERSION",
    "candidate_features",
    "predict_probability",
    "select_calibrated_candidate",
]
