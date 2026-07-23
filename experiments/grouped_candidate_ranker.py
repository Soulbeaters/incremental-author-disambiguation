"""Compact query-group ranker and explicit NIL gate for offline research.

Candidate retrieval stays frozen.  The first model ranks candidates inside one
query; the second decides whether the top candidate is safe enough to link.
Identity labels are used only by the offline trainer and are never serialized
by this module.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np

from disambiguation_engine.listwise_open_set_gate import (
    FEATURE_GROUPS,
    FEATURE_NAMES,
    graph_proposal_features,
)
from evaluation.risk_bounds import chernoff_kl_upper_bound

BASE_RANKER_FEATURE_NAMES = FEATURE_NAMES + (
    "candidate_is_base_merge",
    "candidate_is_graph_proposal",
)
SEMANTIC_FEATURE_NAMES = (
    "paper_to_profile_cosine",
    "paper_to_profile_available",
)
RANKER_FEATURE_NAMES = BASE_RANKER_FEATURE_NAMES + SEMANTIC_FEATURE_NAMES

RANKER_FEATURE_GROUPS = {
    "graph_only": FEATURE_GROUPS["graph_only"] + (len(FEATURE_NAMES), len(FEATURE_NAMES) + 1),
    "pointwise": FEATURE_GROUPS["pointwise"] + (len(FEATURE_NAMES), len(FEATURE_NAMES) + 1),
    "listwise_no_cross_profile": FEATURE_GROUPS["listwise_no_cross_profile"] + (
        len(FEATURE_NAMES),
        len(FEATURE_NAMES) + 1,
    ),
    "listwise_cross_profile": tuple(range(len(BASE_RANKER_FEATURE_NAMES))),
    "listwise_semantic_cross_profile": tuple(range(len(RANKER_FEATURE_NAMES))),
}

GATE_SUMMARY_FEATURE_NAMES = (
    "ranker_top_score",
    "ranker_top_second_margin",
    "ranker_score_entropy",
    "ranker_top_softmax_share",
    "log_ranked_candidate_count",
)
GATE_FEATURE_NAMES = RANKER_FEATURE_NAMES + GATE_SUMMARY_FEATURE_NAMES
FROZEN_MODEL_BUNDLE_SCHEMA = "project2_lightgbm_bundle_v1"


@dataclass(frozen=True)
class CandidateExample:
    author_id: str
    features: tuple[float, ...]
    relevant: bool


@dataclass(frozen=True)
class CandidateGroup:
    position: int
    paper_key: str
    known: bool
    truth: str
    candidates: tuple[CandidateExample, ...]


@dataclass(frozen=True)
class RankedDecision:
    position: int
    paper_key: str
    known: bool
    truth: str
    prediction: str
    features: tuple[float, ...]

    @property
    def correct(self) -> bool:
        return bool(self.known and self.prediction == self.truth)


@dataclass(frozen=True)
class FrozenModelBundle:
    ranker: Any
    nil_gate: Any
    ranker_feature_indices: tuple[int, ...]
    nil_gate_feature_indices: tuple[int, ...]
    decision_threshold: float
    protocol: Mapping[str, Any]


def _require_lightgbm() -> Any:
    try:
        import lightgbm
    except ImportError as exc:  # pragma: no cover - minimal runtime installs
        raise RuntimeError("LightGBM is required; install requirements-training.txt")
    return lightgbm


def _softmax_summary(scores: Sequence[float]) -> tuple[float, float]:
    if not scores:
        return 0.0, 0.0
    maximum = max(scores)
    weights = [math.exp(max(-50.0, float(score) - maximum)) for score in scores]
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


def _unit_embedding(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    vector = np.asarray(value, dtype=np.float32)
    if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
        return None
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return None
    return vector / norm


def _semantic_profile_centroids(
    history_mentions: Sequence[Mapping[str, Any]],
) -> dict[str, np.ndarray]:
    sums: dict[str, np.ndarray] = {}
    paper_vectors: dict[str, np.ndarray | None] = {}
    for position, mention in enumerate(history_mentions):
        author_id = str(
            mention.get("gold_author_id")
            or mention.get("author_id")
            or ""
        )
        paper_key = str(
            mention.get("article_id")
            or mention.get("doi")
            or f"history-{position}"
        )
        if paper_key not in paper_vectors:
            paper_vectors[paper_key] = _unit_embedding(
                mention.get("paper_embedding")
            )
        vector = paper_vectors[paper_key]
        if not author_id or vector is None:
            continue
        if author_id in sums:
            sums[author_id] += vector
        else:
            sums[author_id] = vector.copy()
    centroids = {}
    for author_id, vector_sum in sums.items():
        norm = float(np.linalg.norm(vector_sum))
        if norm > 0.0:
            centroids[author_id] = vector_sum / norm
    return centroids


def gate_feature_indices(
    ranker_indices: Sequence[int],
) -> tuple[int, ...]:
    summary_start = len(RANKER_FEATURE_NAMES)
    return tuple(ranker_indices) + tuple(
        range(summary_start, len(GATE_FEATURE_NAMES))
    )


def build_candidate_groups(replay: Mapping[str, Any]) -> list[CandidateGroup]:
    """Build candidate groups without reading query labels into features."""

    records = list(replay["project2"]["records"])
    graph_proposals = list(replay["native"])
    query_mentions = list(replay.get("test_mentions_raw") or ())
    paper_sizes: Counter[str] = Counter(
        str(record.get("article_id") or position)
        for position, record in enumerate(records)
    )
    fixed_by_paper: Counter[str] = Counter(
        str(record.get("article_id") or position)
        for position, record in enumerate(records)
        if record.get("decision") == "merge"
    )
    profile_years: dict[str, list[int]] = defaultdict(list)
    profile_coauthors: dict[str, set[str]] = defaultdict(set)
    history_mentions = list(replay.get("history_mentions_raw") or ())
    semantic_centroids = _semantic_profile_centroids(history_mentions)
    for mention in history_mentions:
        author_id = str(mention.get("gold_author_id") or mention.get("author_id") or "")
        if not author_id:
            continue
        try:
            year = int(mention.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        if year:
            profile_years[author_id].append(year)
        profile_coauthors[author_id].update(
            str(name)
            for name in mention.get("coauthors") or ()
            if str(name).strip()
        )
    query_embeddings: dict[str, np.ndarray | None] = {}
    query_embedding_by_position: list[np.ndarray | None] = []
    for position, query in enumerate(query_mentions):
        paper_key = str(query.get("article_id") or f"query-{position}")
        if paper_key not in query_embeddings:
            query_embeddings[paper_key] = _unit_embedding(
                query.get("paper_embedding")
            )
        query_embedding_by_position.append(query_embeddings[paper_key])

    groups = []
    for position, (record, graph_proposal) in enumerate(zip(records, graph_proposals)):
        paper_key = str(record.get("article_id") or position)
        query = query_mentions[position] if position < len(query_mentions) else {}
        query_embedding = (
            query_embedding_by_position[position]
            if position < len(query_embedding_by_position)
            else None
        )
        base_author_id = (
            str(record.get("author_id") or "")
            if record.get("decision") == "merge" else ""
        )
        graph_author_id = str(graph_proposal.get("prediction") or "")
        candidate_ids = []
        for candidate in record.get("topk") or ():
            candidate_id = str(candidate.get("author_id") or "")
            if candidate_id and candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
        for candidate_id in (base_author_id, graph_author_id):
            if candidate_id and candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
        if not candidate_ids:
            continue

        truth = str(record.get("gold_author_id") or "")
        candidates = []
        for candidate_id in candidate_ids:
            proposal = {
                "prediction": candidate_id,
                "graph_support": (
                    graph_proposal.get("graph_support")
                    if candidate_id == graph_author_id else 0.0
                ),
                "candidate_count": graph_proposal.get("candidate_count"),
            }
            base_features = graph_proposal_features(
                record,
                proposal,
                profile_size=int(replay["profile_sizes"].get(candidate_id, 0)),
                paper_size=paper_sizes[paper_key],
                fixed_merge_count=fixed_by_paper[paper_key],
                query_year=query.get("year"),
                profile_years=profile_years.get(candidate_id, ()),
                query_coauthors=query.get("coauthors") or (),
                profile_coauthors=profile_coauthors.get(candidate_id, ()),
            )
            centroid = semantic_centroids.get(candidate_id)
            semantic_available = query_embedding is not None and centroid is not None
            semantic_cosine = (
                float(np.clip(np.dot(query_embedding, centroid), -1.0, 1.0))
                if semantic_available else 0.0
            )
            candidates.append(CandidateExample(
                author_id=candidate_id,
                features=base_features + (
                    float(candidate_id == base_author_id),
                    float(candidate_id == graph_author_id),
                    semantic_cosine,
                    float(semantic_available),
                ),
                relevant=bool(
                    record.get("gold_seen_in_history") and candidate_id == truth
                ),
            ))
        groups.append(CandidateGroup(
            position=position,
            paper_key=paper_key,
            known=bool(record.get("gold_seen_in_history")),
            truth=truth,
            candidates=tuple(candidates),
        ))
    return groups


def _ranker_training_arrays(
    groups: Sequence[CandidateGroup],
    indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    eligible = [group for group in groups if any(row.relevant for row in group.candidates)]
    features = np.asarray([
        [row.features[index] for index in indices]
        for group in eligible
        for row in group.candidates
    ], dtype=float)
    labels = np.asarray([
        int(row.relevant)
        for group in eligible
        for row in group.candidates
    ], dtype=int)
    sizes = [len(group.candidates) for group in eligible]
    if not sizes or not labels.any() or labels.all():
        raise ValueError("ranker training requires query groups with positive and negative candidates")
    return features, labels, sizes


def fit_ranker(
    groups: Sequence[CandidateGroup],
    indices: Sequence[int],
    *,
    seed: int = 20260722,
) -> Any:
    library = _require_lightgbm()
    features, labels, sizes = _ranker_training_arrays(groups, indices)
    model = library.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=120,
        learning_rate=0.05,
        num_leaves=15,
        max_depth=4,
        min_child_samples=20,
        reg_lambda=2.0,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        n_jobs=1,
        verbosity=-1,
    )
    model.fit(features, labels, group=sizes)
    return model


def rank_groups(
    model: Any,
    groups: Sequence[CandidateGroup],
    indices: Sequence[int],
) -> list[RankedDecision]:
    decisions = []
    for group in groups:
        features = np.asarray([
            [row.features[index] for index in indices]
            for row in group.candidates
        ], dtype=float)
        scores = [float(value) for value in model.predict(features)]
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        top_index = order[0]
        top_score = scores[top_index]
        second_score = scores[order[1]] if len(order) > 1 else top_score
        entropy, top_share = _softmax_summary(scores)
        top = group.candidates[top_index]
        decisions.append(RankedDecision(
            position=group.position,
            paper_key=group.paper_key,
            known=group.known,
            truth=group.truth,
            prediction=top.author_id,
            features=top.features + (
                top_score,
                top_score - second_score,
                entropy,
                top_share,
                math.log1p(len(group.candidates)),
            ),
        ))
    return decisions


def _paper_fold(paper_key: str, folds: int) -> int:
    digest = hashlib.sha256(paper_key.casefold().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % folds


def out_of_fold_ranked_decisions(
    groups: Sequence[CandidateGroup],
    indices: Sequence[int],
    *,
    folds: int,
) -> list[RankedDecision]:
    if folds < 2:
        raise ValueError("out-of-fold ranking needs at least two folds")
    output = []
    for fold in range(folds):
        training = [group for group in groups if _paper_fold(group.paper_key, folds) != fold]
        held_out = [group for group in groups if _paper_fold(group.paper_key, folds) == fold]
        if not held_out:
            continue
        model = fit_ranker(training, indices, seed=20260722 + fold)
        output.extend(rank_groups(model, held_out, indices))
    return sorted(output, key=lambda decision: decision.position)


def fit_nil_gate(
    decisions: Sequence[RankedDecision],
    indices: Sequence[int] | None = None,
    *,
    seed: int = 20260722,
) -> Any:
    library = _require_lightgbm()
    selected = tuple(indices) if indices is not None else tuple(
        range(len(GATE_FEATURE_NAMES))
    )
    features = np.asarray([
        [decision.features[index] for index in selected]
        for decision in decisions
    ], dtype=float)
    labels = np.asarray([int(decision.correct) for decision in decisions], dtype=int)
    if not labels.any() or labels.all():
        raise ValueError("NIL gate training needs safe links and rejection examples")
    weights = np.asarray([
        0.25 if decision.correct else 1.5 if decision.known else 1.0
        for decision in decisions
    ], dtype=float)
    model = library.LGBMClassifier(
        objective="binary",
        n_estimators=120,
        learning_rate=0.04,
        num_leaves=7,
        max_depth=3,
        min_child_samples=10,
        reg_lambda=3.0,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        n_jobs=1,
        verbosity=-1,
    )
    model.fit(features, labels, sample_weight=weights)
    return model


def gate_scores(
    model: Any,
    decisions: Sequence[RankedDecision],
    indices: Sequence[int] | None = None,
) -> dict[int, float]:
    selected = tuple(indices) if indices is not None else tuple(
        range(len(GATE_FEATURE_NAMES))
    )
    features = np.asarray([
        [decision.features[index] for index in selected]
        for decision in decisions
    ], dtype=float)
    if hasattr(model, "predict_proba"):
        probabilities = np.asarray(model.predict_proba(features), dtype=float)[:, 1]
    else:
        probabilities = np.asarray(model.predict(features), dtype=float)
        if probabilities.ndim != 1:
            raise ValueError("frozen NIL gate must return one probability per row")
    return {
        decision.position: float(probability)
        for decision, probability in zip(decisions, probabilities)
    }


def training_score_thresholds(
    scores: Sequence[float],
    *,
    grid_size: int,
) -> tuple[float, ...]:
    """Fix a conservative-to-liberal threshold family from training scores."""

    if grid_size < 2:
        raise ValueError("training threshold grid needs at least two points")
    ordered = sorted(float(score) for score in scores)
    if not ordered:
        raise ValueError("training threshold grid needs non-empty scores")
    positions = {
        round(index * (len(ordered) - 1) / (grid_size - 1))
        for index in range(grid_size)
    }
    thresholds = {ordered[position] for position in positions}
    thresholds.add(math.nextafter(1.0, math.inf))
    return tuple(sorted(thresholds, reverse=True))


def _threshold_operating_points(
    decisions: Sequence[RankedDecision],
    scores: Mapping[int, float],
    candidate_thresholds: Sequence[float] | None,
) -> list[tuple[float, int, int, int, int]]:
    ordered = sorted(decisions, key=lambda row: scores[row.position], reverse=True)
    if candidate_thresholds is not None:
        thresholds = sorted(
            {float(threshold) for threshold in candidate_thresholds},
            reverse=True,
        )
        if not thresholds:
            raise ValueError("candidate threshold family must not be empty")
        output = []
        for threshold in thresholds:
            selected = [
                decision
                for decision in ordered
                if scores[decision.position] >= threshold
            ]
            output.append((
                threshold,
                len(selected),
                sum(decision.correct for decision in selected),
                sum(
                    decision.known and not decision.correct
                    for decision in selected
                ),
                sum(not decision.known for decision in selected),
            ))
        return output

    max_score = scores[ordered[0].position] if ordered else 0.0
    output = [(math.nextafter(max_score, math.inf), 0, 0, 0, 0)]
    accepted = correct = wrong_known = new_false = 0
    cursor = 0
    while cursor < len(ordered):
        threshold = scores[ordered[cursor].position]
        while cursor < len(ordered) and scores[ordered[cursor].position] == threshold:
            decision = ordered[cursor]
            accepted += 1
            correct += int(decision.correct)
            wrong_known += int(decision.known and not decision.correct)
            new_false += int(not decision.known)
            cursor += 1
        output.append((threshold, accepted, correct, wrong_known, new_false))
    return output


def select_risk_bounded_threshold(
    decisions: Sequence[RankedDecision],
    scores: Mapping[int, float],
    *,
    known_trials: int,
    new_trials: int,
    confidence: float,
    max_new_false_rate: float,
    max_wrong_known_rate: float,
    candidate_thresholds: Sequence[float] | None = None,
    testing_method: str = "bonferroni",
) -> dict[str, Any]:
    """Select a risk-bounded threshold with a valid learn-then-test procedure."""

    if testing_method not in {"bonferroni", "fixed_sequence"}:
        raise ValueError("unsupported threshold testing method")
    operating_points = _threshold_operating_points(
        decisions,
        scores,
        candidate_thresholds,
    )
    pointwise_confidence = (
        confidence
        if testing_method == "fixed_sequence"
        else 1.0 - (1.0 - confidence) / len(operating_points)
    )
    best = None
    tested_points = 0
    for threshold, accepted, correct, wrong_known, new_false in operating_points:
        tested_points += 1
        new_upper = chernoff_kl_upper_bound(
            new_false, new_trials, confidence=pointwise_confidence
        )
        wrong_upper = chernoff_kl_upper_bound(
            wrong_known, known_trials, confidence=pointwise_confidence
        )
        passed = (
            new_upper <= max_new_false_rate
            and wrong_upper <= max_wrong_known_rate
        )
        if not passed and testing_method == "fixed_sequence":
            break
        if not passed:
            continue
        candidate = (correct, -(wrong_known + new_false), -accepted, threshold)
        if testing_method == "fixed_sequence":
            best = candidate
        elif best is None or candidate > best:
            best = candidate
    if best is None:
        raise ValueError("no ranker/NIL threshold satisfies the familywise risk budget")
    threshold = float(best[3])
    selected = [decision for decision in decisions if scores[decision.position] >= threshold]
    selected_wrong = sum(decision.known and not decision.correct for decision in selected)
    selected_new = sum(not decision.known for decision in selected)
    return {
        "threshold": threshold,
        "accepted": len(selected),
        "correct_known": sum(decision.correct for decision in selected),
        "wrong_known": selected_wrong,
        "new_false_links": selected_new,
        "coverage": len(selected) / (known_trials + new_trials) if known_trials + new_trials else 0.0,
        "testing_method": testing_method,
        "threshold_family_source": (
            "training_scores" if candidate_thresholds is not None
            else "selection_scores"
        ),
        "familywise_confidence": confidence,
        "operating_points": len(operating_points),
        "tested_points": tested_points,
        "pointwise_confidence": pointwise_confidence,
        "new_false_link_upper_bound": chernoff_kl_upper_bound(
            selected_new, new_trials, confidence=pointwise_confidence
        ),
        "wrong_known_upper_bound": chernoff_kl_upper_bound(
            selected_wrong, known_trials, confidence=pointwise_confidence
        ),
    }


def threshold_predictions(
    total: int,
    decisions: Sequence[RankedDecision],
    scores: Mapping[int, float],
    threshold: float,
) -> list[str | None]:
    output: list[str | None] = [None] * total
    for decision in decisions:
        if scores[decision.position] >= threshold:
            output[decision.position] = decision.prediction
    return output


def ranking_metrics(
    groups: Sequence[CandidateGroup],
    decisions: Sequence[RankedDecision],
    *,
    known_trials: int | None = None,
    new_trials: int | None = None,
) -> dict[str, Any]:
    known_groups = [group for group in groups if group.known]
    covered = sum(any(row.relevant for row in group.candidates) for group in known_groups)
    input_top1 = sum(group.candidates[0].relevant for group in known_groups)
    top1 = sum(decision.correct for decision in decisions)
    total_known = known_trials if known_trials is not None else len(known_groups)
    total_queries = (
        total_known + int(new_trials or 0)
        if known_trials is not None else len(groups)
    )
    return {
        "queries_with_candidates": len(groups),
        "total_queries": total_queries,
        "known_queries_with_candidates": len(known_groups),
        "total_known_queries": total_known,
        "known_candidate_covered": covered,
        "candidate_recall_within_nonempty": (
            covered / len(known_groups) if known_groups else 0.0
        ),
        "candidate_recall_overall": covered / total_known if total_known else 0.0,
        "input_order_top1_correct": input_top1,
        "input_order_top1_known_accuracy": (
            input_top1 / total_known if total_known else 0.0
        ),
        "top1_correct": top1,
        "top1_known_accuracy_within_nonempty": (
            top1 / len(known_groups) if known_groups else 0.0
        ),
        "top1_known_accuracy_overall": top1 / total_known if total_known else 0.0,
        "mean_candidates": (
            sum(len(group.candidates) for group in groups) / len(groups)
            if groups else 0.0
        ),
        "max_candidates": max((len(group.candidates) for group in groups), default=0),
    }


def model_summary(model: Any, feature_names: Sequence[str]) -> dict[str, Any]:
    if hasattr(model, "feature_importances_"):
        importances = [int(value) for value in model.feature_importances_]
        trees = int(getattr(model, "n_estimators", 0))
    else:
        importances = [
            int(value) for value in model.feature_importance(importance_type="split")
        ]
        trees = int(model.num_trees())
    ranked = sorted(
        zip(feature_names, importances),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "model_class": type(model).__name__,
        "trees": trees,
        "feature_count": len(feature_names),
        "feature_importance_split": [
            {"feature": name, "importance": importance}
            for name, importance in ranked
        ],
    }


def _validated_feature_indices(
    values: Sequence[int],
    names: Sequence[str],
    *,
    role: str,
) -> tuple[int, ...]:
    indices = tuple(int(value) for value in values)
    if (
        not indices
        or len(indices) != len(set(indices))
        or any(index < 0 or index >= len(names) for index in indices)
    ):
        raise ValueError(f"invalid {role} feature indices")
    return indices


def _booster_model_string(model: Any, *, role: str) -> str:
    booster = getattr(model, "booster_", model)
    if not hasattr(booster, "model_to_string"):
        raise ValueError(f"{role} is not a fitted LightGBM model")
    value = str(booster.model_to_string())
    if not value.strip():
        raise ValueError(f"{role} produced an empty LightGBM model")
    return value


def freeze_model_bundle(
    ranker: Any,
    nil_gate: Any,
    ranker_feature_indices: Sequence[int],
    nil_gate_feature_indices: Sequence[int],
    decision_threshold: float,
    *,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a portable, label-free LightGBM model bundle."""

    ranker_indices = _validated_feature_indices(
        ranker_feature_indices,
        RANKER_FEATURE_NAMES,
        role="ranker",
    )
    gate_indices = _validated_feature_indices(
        nil_gate_feature_indices,
        GATE_FEATURE_NAMES,
        role="NIL gate",
    )
    threshold = float(decision_threshold)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("decision threshold must be finite and non-negative")
    protocol_payload = dict(protocol)
    forbidden_protocol_keys = {
        "gold_author_id",
        "person_id",
        "identity",
        "labels",
        "record_values",
    }

    def reject_identity_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if str(key).casefold() in forbidden_protocol_keys:
                    raise ValueError("frozen model protocol contains identity fields")
                reject_identity_keys(nested)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                reject_identity_keys(nested)

    reject_identity_keys(protocol_payload)
    encoded_protocol = json.dumps(
        protocol_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    ranker_model = _booster_model_string(ranker, role="ranker")
    gate_model = _booster_model_string(nil_gate, role="NIL gate")

    def component(
        model_string: str,
        indices: tuple[int, ...],
        names: Sequence[str],
    ) -> dict[str, Any]:
        return {
            "feature_indices": list(indices),
            "feature_names": [names[index] for index in indices],
            "model_sha256": hashlib.sha256(
                model_string.encode("utf-8")
            ).hexdigest(),
            "lightgbm_model": model_string,
        }

    return {
        "schema_version": FROZEN_MODEL_BUNDLE_SCHEMA,
        "contains_identity_values": False,
        "decision_threshold": threshold,
        "protocol_sha256": hashlib.sha256(encoded_protocol).hexdigest(),
        "ranker": component(
            ranker_model,
            ranker_indices,
            RANKER_FEATURE_NAMES,
        ),
        "nil_gate": component(
            gate_model,
            gate_indices,
            GATE_FEATURE_NAMES,
        ),
        "protocol": protocol_payload,
    }


def load_frozen_model_bundle(payload: Mapping[str, Any]) -> FrozenModelBundle:
    """Validate and load a bundle without executing pickle content."""

    if payload.get("schema_version") != FROZEN_MODEL_BUNDLE_SCHEMA:
        raise ValueError("unsupported frozen model bundle schema")
    if payload.get("contains_identity_values") is not False:
        raise ValueError("frozen model bundle identity-safety marker is missing")
    library = _require_lightgbm()

    def load_component(
        role: str,
        all_names: Sequence[str],
    ) -> tuple[Any, tuple[int, ...]]:
        component = payload.get(role)
        if not isinstance(component, Mapping):
            raise ValueError(f"missing frozen {role} component")
        indices = _validated_feature_indices(
            component.get("feature_indices") or (),
            all_names,
            role=role,
        )
        expected_names = [all_names[index] for index in indices]
        if component.get("feature_names") != expected_names:
            raise ValueError(f"frozen {role} feature names do not match runtime")
        model_string = component.get("lightgbm_model")
        if not isinstance(model_string, str) or not model_string.strip():
            raise ValueError(f"missing frozen {role} LightGBM model")
        expected_hash = hashlib.sha256(model_string.encode("utf-8")).hexdigest()
        if component.get("model_sha256") != expected_hash:
            raise ValueError(f"frozen {role} model hash mismatch")
        booster = library.Booster(model_str=model_string)
        if booster.num_feature() != len(indices):
            raise ValueError(f"frozen {role} feature count mismatch")
        return booster, indices

    threshold = float(payload.get("decision_threshold"))
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("invalid frozen decision threshold")
    ranker, ranker_indices = load_component("ranker", RANKER_FEATURE_NAMES)
    nil_gate, nil_gate_indices = load_component("nil_gate", GATE_FEATURE_NAMES)
    protocol = payload.get("protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("frozen model protocol is missing")
    encoded_protocol = json.dumps(
        protocol,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if payload.get("protocol_sha256") != hashlib.sha256(
        encoded_protocol
    ).hexdigest():
        raise ValueError("frozen model protocol hash mismatch")
    return FrozenModelBundle(
        ranker=ranker,
        nil_gate=nil_gate,
        ranker_feature_indices=ranker_indices,
        nil_gate_feature_indices=nil_gate_indices,
        decision_threshold=threshold,
        protocol=dict(protocol),
    )


__all__ = [
    "CandidateExample",
    "CandidateGroup",
    "FROZEN_MODEL_BUNDLE_SCHEMA",
    "FrozenModelBundle",
    "GATE_FEATURE_NAMES",
    "RANKER_FEATURE_GROUPS",
    "RANKER_FEATURE_NAMES",
    "RankedDecision",
    "build_candidate_groups",
    "fit_nil_gate",
    "fit_ranker",
    "freeze_model_bundle",
    "gate_feature_indices",
    "gate_scores",
    "model_summary",
    "out_of_fold_ranked_decisions",
    "rank_groups",
    "ranking_metrics",
    "load_frozen_model_bundle",
    "select_risk_bounded_threshold",
    "threshold_predictions",
    "training_score_thresholds",
]
