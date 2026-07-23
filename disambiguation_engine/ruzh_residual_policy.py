"""Residual correction policy above a frozen official disambiguator."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .ruzh_conditional_expert import LinkOutcomeCounts, joint_promotion_gate


@dataclass(frozen=True, slots=True)
class ResidualRow:
    query_key: str
    target: bool
    known: bool
    truth: str
    official: str | None
    expert: str | None
    features: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ResidualModels:
    replacement: Any
    veto: Any


@dataclass(frozen=True, slots=True)
class ResidualPolicy:
    replacement_threshold: float
    veto_threshold: float


def _require_lightgbm() -> Any:
    try:
        import lightgbm
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("LightGBM is required for the residual policy") from exc
    return lightgbm


def replacement_eligible(row: ResidualRow) -> bool:
    return bool(
        row.target
        and row.expert is not None
        and row.expert != row.official
        and row.features
    )


def veto_eligible(row: ResidualRow) -> bool:
    return bool(row.target and row.official is not None and row.features)


def _replacement_label(row: ResidualRow) -> int:
    return int(row.known and row.expert == row.truth and row.official != row.truth)


def _veto_label(row: ResidualRow) -> int:
    official_correct = row.known and row.official == row.truth
    return int(row.official is not None and not official_correct)


def _fit_classifier(
    rows: Sequence[ResidualRow],
    labels: Sequence[int],
    *,
    seed: int,
) -> Any:
    if not rows or len(rows) != len(labels):
        raise ValueError("residual classifier inputs are empty or misaligned")
    if not any(labels) or all(labels):
        raise ValueError("residual classifier needs both action outcomes")
    library = _require_lightgbm()
    features = np.asarray([row.features for row in rows], dtype=float)
    values = np.asarray(labels, dtype=int)
    positive = max(1, int(values.sum()))
    negative = max(1, len(values) - positive)
    weights = np.asarray([
        len(values) / (2.0 * positive) if label
        else len(values) / (2.0 * negative)
        for label in values
    ])
    model = library.LGBMClassifier(
        objective="binary",
        n_estimators=100,
        learning_rate=0.04,
        num_leaves=7,
        max_depth=3,
        min_child_samples=20,
        reg_lambda=3.0,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        n_jobs=1,
        verbosity=-1,
    )
    model.fit(features, values, sample_weight=weights)
    return model


def fit_residual_models(
    rows: Sequence[ResidualRow],
    *,
    seed: int = 20260723,
) -> ResidualModels:
    replacement_rows = [row for row in rows if replacement_eligible(row)]
    veto_rows = [row for row in rows if veto_eligible(row)]
    return ResidualModels(
        replacement=_fit_classifier(
            replacement_rows,
            [_replacement_label(row) for row in replacement_rows],
            seed=seed,
        ),
        veto=_fit_classifier(
            veto_rows,
            [_veto_label(row) for row in veto_rows],
            seed=seed + 1,
        ),
    )


def _positive_scores(model: Any, rows: Sequence[ResidualRow]) -> list[float]:
    if not rows:
        return []
    features = np.asarray([row.features for row in rows], dtype=float)
    if hasattr(model, "predict_proba"):
        values = np.asarray(model.predict_proba(features), dtype=float)[:, 1]
    else:
        values = np.asarray(model.predict(features), dtype=float)
    return [float(value) for value in values]


def score_residual_actions(
    models: ResidualModels,
    rows: Sequence[ResidualRow],
) -> tuple[dict[str, float], dict[str, float]]:
    replacement_rows = [row for row in rows if replacement_eligible(row)]
    veto_rows = [row for row in rows if veto_eligible(row)]
    replacement = dict(zip(
        (row.query_key for row in replacement_rows),
        _positive_scores(models.replacement, replacement_rows),
    ))
    veto = dict(zip(
        (row.query_key for row in veto_rows),
        _positive_scores(models.veto, veto_rows),
    ))
    return replacement, veto


def threshold_family(
    scores: Sequence[float],
    *,
    size: int = 12,
) -> tuple[float, ...]:
    """Freeze a conservative-to-liberal family from training scores only."""

    if size < 2:
        raise ValueError("threshold family needs at least two points")
    ordered = sorted(float(value) for value in scores)
    if not ordered:
        raise ValueError("threshold family needs training scores")
    thresholds = [math.inf]
    for index in range(size - 1):
        fraction = index / max(1, size - 2)
        position = round((1.0 - fraction) * (len(ordered) - 1))
        thresholds.append(ordered[position])
    return tuple(dict.fromkeys(thresholds))


def apply_residual_policy(
    rows: Sequence[ResidualRow],
    replacement_scores: Mapping[str, float],
    veto_scores: Mapping[str, float],
    policy: ResidualPolicy,
) -> list[str | None]:
    output = []
    for row in rows:
        prediction = row.official
        if (
            replacement_eligible(row)
            and float(replacement_scores.get(row.query_key, -math.inf))
            >= policy.replacement_threshold
        ):
            prediction = row.expert
        elif (
            veto_eligible(row)
            and float(veto_scores.get(row.query_key, -math.inf))
            >= policy.veto_threshold
        ):
            prediction = None
        output.append(prediction)
    return output


def link_outcomes(
    rows: Sequence[ResidualRow],
    predictions: Sequence[str | None],
    *,
    target: bool,
) -> LinkOutcomeCounts:
    selected = [
        (row, prediction)
        for row, prediction in zip(rows, predictions, strict=True)
        if row.target is target
    ]
    known = sum(row.known for row, _prediction in selected)
    new = len(selected) - known
    return LinkOutcomeCounts(
        known=known,
        new=new,
        correct_known=sum(
            row.known and prediction == row.truth
            for row, prediction in selected
        ),
        wrong_known=sum(
            row.known
            and prediction is not None
            and prediction != row.truth
            for row, prediction in selected
        ),
        false_links_new=sum(
            not row.known and prediction is not None
            for row, prediction in selected
        ),
    )


def select_residual_policy(
    rows: Sequence[ResidualRow],
    replacement_scores: Mapping[str, float],
    veto_scores: Mapping[str, float],
    replacement_thresholds: Sequence[float],
    veto_thresholds: Sequence[float],
) -> tuple[ResidualPolicy, Mapping[str, int]]:
    official = [row.official for row in rows]
    target_baseline = link_outcomes(rows, official, target=True)
    non_target_trials = sum(not row.target for row in rows)
    best: tuple[tuple[int, ...], ResidualPolicy, Mapping[str, int]] | None = None
    for replacement_threshold in replacement_thresholds:
        for veto_threshold in veto_thresholds:
            policy = ResidualPolicy(
                float(replacement_threshold),
                float(veto_threshold),
            )
            candidate = apply_residual_policy(
                rows,
                replacement_scores,
                veto_scores,
                policy,
            )
            non_target_disagreements = sum(
                not row.target and prediction != row.official
                for row, prediction in zip(rows, candidate, strict=True)
            )
            target_candidate = link_outcomes(rows, candidate, target=True)
            gate = joint_promotion_gate(
                target_baseline,
                target_candidate,
                non_target_trials=non_target_trials,
                non_target_disagreements=non_target_disagreements,
            )
            if not gate.passed:
                continue
            deltas = dict(gate.deltas)
            total_improvement = (
                deltas["correct_known"]
                - deltas["wrong_known"]
                - deltas["false_links_new"]
            )
            changes = sum(
                prediction != row.official
                for row, prediction in zip(rows, candidate, strict=True)
            )
            rank = (
                total_improvement,
                deltas["correct_known"],
                -deltas["wrong_known"],
                -deltas["false_links_new"],
                -changes,
            )
            if best is None or rank > best[0]:
                best = rank, policy, deltas
    if best is None:
        raise ValueError("no residual policy passes validation non-regression")
    return best[1], best[2]


__all__ = [
    "ResidualModels",
    "ResidualPolicy",
    "ResidualRow",
    "apply_residual_policy",
    "fit_residual_models",
    "link_outcomes",
    "replacement_eligible",
    "score_residual_actions",
    "select_residual_policy",
    "threshold_family",
    "veto_eligible",
]
