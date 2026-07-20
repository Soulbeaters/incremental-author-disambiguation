"""Fit and verify the frozen calibrated candidate-risk model.

The training replay must be produced with calibrated rescue disabled. Candidate
rows are weighted equally per mention, an L2-regularized logistic model is fit
with deterministic Newton updates, and one acceptance threshold is selected on
a separate validation replay under an unseen-author false-link budget.

NumPy is required only for offline fitting. Runtime inference remains standard
library-only in :mod:`disambiguation_engine.calibrated_candidate_model`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.calibrated_candidate_model import (  # noqa: E402
    COEFFICIENTS,
    DEFAULT_ACCEPT_THRESHOLD,
    FEATURE_MEAN,
    FEATURE_SCALE,
    MODEL_VERSION,
    candidate_features,
)


def load_result(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def training_rows(
    document: Mapping[str, Any],
    topk_limit: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    features: List[Sequence[float]] = []
    labels: List[float] = []
    weights: List[float] = []
    for record in document.get("records") or []:
        candidates = list(record.get("topk") or [])[:topk_limit]
        if not candidates:
            continue
        row_weight = 1.0 / len(candidates)
        for rank, candidate in enumerate(candidates):
            features.append(candidate_features(
                mention_name=str(record.get("name") or ""),
                stage=str(record.get("stage") or ""),
                candidate_count=int(record.get("candidate_count") or 0),
                candidates=candidates,
                candidate=candidate,
                rank=rank,
            ))
            labels.append(float(
                record.get("gold_seen_in_history")
                and str(candidate.get("author_id") or "")
                == str(record.get("gold_author_id") or "")
            ))
            weights.append(row_weight)
    if not features:
        raise ValueError("training replay contains no candidate rows")
    return (
        np.asarray(features, dtype=float),
        np.asarray(labels, dtype=float),
        np.asarray(weights, dtype=float),
    )


def fit_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    sample_weight: np.ndarray,
    l2: float = 1.0,
    iterations: int = 50,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (features - mean) / scale
    design = np.column_stack([np.ones(len(standardized)), standardized])
    coefficients = np.zeros(design.shape[1])
    penalty = np.eye(design.shape[1]) * l2
    penalty[0, 0] = 0.0

    for _ in range(iterations):
        linear = np.clip(design @ coefficients, -35.0, 35.0)
        probability = 1.0 / (1.0 + np.exp(-linear))
        curvature = sample_weight * probability * (1.0 - probability)
        hessian = design.T @ (design * curvature[:, None]) + penalty
        gradient = (
            design.T @ ((probability - labels) * sample_weight)
            + penalty @ coefficients
        )
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return mean, scale, coefficients


def probability(
    values: Sequence[float],
    mean: np.ndarray,
    scale: np.ndarray,
    coefficients: np.ndarray,
) -> float:
    standardized = (np.asarray(values, dtype=float) - mean) / scale
    linear = float(coefficients[0] + standardized @ coefficients[1:])
    linear = max(-35.0, min(35.0, linear))
    return 1.0 / (1.0 + math.exp(-linear))


def validation_rescues(
    document: Mapping[str, Any],
    topk_limit: int,
    model: Tuple[np.ndarray, np.ndarray, np.ndarray],
) -> List[Dict[str, Any]]:
    mean, scale, coefficients = model
    output = []
    for record in document.get("records") or []:
        if record.get("decision") == "merge":
            continue
        candidates = list(record.get("topk") or [])[:topk_limit]
        if not candidates:
            continue
        scored = [
            (
                probability(
                    candidate_features(
                        mention_name=str(record.get("name") or ""),
                        stage=str(record.get("stage") or ""),
                        candidate_count=int(record.get("candidate_count") or 0),
                        candidates=candidates,
                        candidate=candidate,
                        rank=rank,
                    ),
                    mean,
                    scale,
                    coefficients,
                ),
                candidate,
            )
            for rank, candidate in enumerate(candidates)
        ]
        score, candidate = max(scored, key=lambda item: item[0])
        output.append({
            "probability": score,
            "correct": bool(
                record.get("gold_seen_in_history")
                and str(candidate.get("author_id") or "")
                == str(record.get("gold_author_id") or "")
            ),
            "unseen": not bool(record.get("gold_seen_in_history")),
        })
    return output


def choose_threshold(
    document: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    max_unseen_false: int,
) -> Dict[str, Any]:
    stats = document.get("stats") or {}
    best: Tuple[int, int, float, int, float, float, int] | None = None
    for threshold in sorted({float(row["probability"]) for row in rows}, reverse=True):
        accepted = [row for row in rows if row["probability"] >= threshold]
        correct = sum(bool(row["correct"]) for row in accepted)
        wrong = len(accepted) - correct
        unseen_false = sum(bool(row["unseen"]) for row in accepted)
        if unseen_false > max_unseen_false:
            continue
        recall = (int(stats["correct_merge"]) + correct) / int(stats["existing_gold"])
        precision = (int(stats["correct_merge"]) + correct) / (
            int(stats["merge"]) + len(accepted)
        )
        candidate = (
            correct,
            -wrong,
            threshold,
            unseen_false,
            recall,
            precision,
            len(accepted),
        )
        if best is None or candidate > best:
            best = candidate
    if best is None:
        raise ValueError("no validation threshold satisfies the false-link budget")
    return {
        "correct_rescues": best[0],
        "wrong_rescues": -best[1],
        "threshold": best[2],
        "unseen_false_links": best[3],
        "projected_existing_recall": best[4],
        "projected_merge_precision": best[5],
        "accepted": best[6],
    }


def max_delta(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(float(a) - float(b)) for a, b in zip(left, right))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-result", type=Path, required=True)
    parser.add_argument("--validation-result", type=Path, required=True)
    parser.add_argument("--topk", type=int, default=20)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--max-unseen-false-rate", type=float, default=0.001)
    parser.add_argument("--verify-runtime-model", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    train = load_result(args.train_result)
    validation = load_result(args.validation_result)
    features, labels, weights = training_rows(train, args.topk)
    model = fit_logistic(
        features,
        labels,
        weights,
        l2=args.l2,
        iterations=args.iterations,
    )
    rows = validation_rescues(validation, args.topk, model)
    new_gold = int((validation.get("stats") or {}).get("new_gold") or 0)
    max_unseen_false = math.floor(new_gold * args.max_unseen_false_rate)
    threshold = choose_threshold(validation, rows, max_unseen_false)
    mean, scale, coefficients = model
    verification = {
        "model_version": MODEL_VERSION,
        "mean_max_abs_delta": max_delta(mean, FEATURE_MEAN),
        "scale_max_abs_delta": max_delta(scale, FEATURE_SCALE),
        "coefficient_max_abs_delta": max_delta(coefficients, COEFFICIENTS),
        "threshold_abs_delta": abs(
            threshold["threshold"] - DEFAULT_ACCEPT_THRESHOLD
        ),
    }
    verification["matches_runtime"] = all(
        value <= 1e-12
        for key, value in verification.items()
        if key.endswith("delta")
    )
    artifact = {
        "protocol": {
            "train_result": str(args.train_result),
            "validation_result": str(args.validation_result),
            "topk": args.topk,
            "l2": args.l2,
            "iterations": args.iterations,
            "max_unseen_false_rate": args.max_unseen_false_rate,
            "max_unseen_false": max_unseen_false,
            "mention_balanced_candidate_weights": True,
        },
        "training_rows": len(features),
        "positive_rows": int(labels.sum()),
        "validation_rescue_rows": len(rows),
        "threshold_selection": threshold,
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "runtime_verification": verification,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    if args.verify_runtime_model and not verification["matches_runtime"]:
        raise SystemExit("fitted model does not match frozen runtime constants")


if __name__ == "__main__":
    main()
