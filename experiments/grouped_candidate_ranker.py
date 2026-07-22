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
import math
from typing import Any, Mapping, Sequence

import numpy as np

from disambiguation_engine.listwise_open_set_gate import (
    FEATURE_GROUPS,
    FEATURE_NAMES,
    graph_proposal_features,
)
from evaluation.risk_bounds import chernoff_kl_upper_bound

RANKER_FEATURE_NAMES = FEATURE_NAMES + (
    "candidate_is_base_merge",
    "candidate_is_graph_proposal",
)

RANKER_FEATURE_GROUPS = {
    "graph_only": FEATURE_GROUPS["graph_only"] + (len(FEATURE_NAMES), len(FEATURE_NAMES) + 1),
    "pointwise": FEATURE_GROUPS["pointwise"] + (len(FEATURE_NAMES), len(FEATURE_NAMES) + 1),
    "listwise_no_cross_profile": FEATURE_GROUPS["listwise_no_cross_profile"] + (
        len(FEATURE_NAMES),
        len(FEATURE_NAMES) + 1,
    ),
    "listwise_cross_profile": tuple(range(len(RANKER_FEATURE_NAMES))),
}

GATE_SUMMARY_FEATURE_NAMES = (
    "ranker_top_score",
    "ranker_top_second_margin",
    "ranker_score_entropy",
    "ranker_top_softmax_share",
    "log_ranked_candidate_count",
)
GATE_FEATURE_NAMES = RANKER_FEATURE_NAMES + GATE_SUMMARY_FEATURE_NAMES


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
    for mention in replay.get("history_mentions_raw") or ():
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

    groups = []
    for position, (record, graph_proposal) in enumerate(zip(records, graph_proposals)):
        paper_key = str(record.get("article_id") or position)
        query = query_mentions[position] if position < len(query_mentions) else {}
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
            candidates.append(CandidateExample(
                author_id=candidate_id,
                features=base_features + (
                    float(candidate_id == base_author_id),
                    float(candidate_id == graph_author_id),
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
    *,
    seed: int = 20260722,
) -> Any:
    library = _require_lightgbm()
    features = np.asarray([decision.features for decision in decisions], dtype=float)
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


def gate_scores(model: Any, decisions: Sequence[RankedDecision]) -> dict[int, float]:
    features = np.asarray([decision.features for decision in decisions], dtype=float)
    probabilities = model.predict_proba(features)[:, 1]
    return {
        decision.position: float(probability)
        for decision, probability in zip(decisions, probabilities)
    }


def select_risk_bounded_threshold(
    decisions: Sequence[RankedDecision],
    scores: Mapping[int, float],
    *,
    known_trials: int,
    new_trials: int,
    confidence: float,
    max_new_false_rate: float,
    max_wrong_known_rate: float,
) -> dict[str, Any]:
    """Learn-then-test threshold family with Bonferroni risk control."""

    ordered = sorted(decisions, key=lambda row: scores[row.position], reverse=True)
    max_score = scores[ordered[0].position] if ordered else 0.0
    operating_points = [(math.nextafter(max_score, math.inf), 0, 0, 0, 0)]
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
        operating_points.append((threshold, accepted, correct, wrong_known, new_false))

    pointwise_confidence = 1.0 - (1.0 - confidence) / len(operating_points)
    best = None
    for threshold, accepted, correct, wrong_known, new_false in operating_points:
        new_upper = chernoff_kl_upper_bound(
            new_false, new_trials, confidence=pointwise_confidence
        )
        wrong_upper = chernoff_kl_upper_bound(
            wrong_known, known_trials, confidence=pointwise_confidence
        )
        if new_upper > max_new_false_rate or wrong_upper > max_wrong_known_rate:
            continue
        candidate = (correct, -(wrong_known + new_false), -accepted, threshold)
        if best is None or candidate > best:
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
        "familywise_confidence": confidence,
        "operating_points": len(operating_points),
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
    importances = [int(value) for value in model.feature_importances_]
    ranked = sorted(
        zip(feature_names, importances),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "model_class": type(model).__name__,
        "trees": int(getattr(model, "n_estimators", 0)),
        "feature_count": len(feature_names),
        "feature_importance_split": [
            {"feature": name, "importance": importance}
            for name, importance in ranked
        ],
    }


__all__ = [
    "CandidateExample",
    "CandidateGroup",
    "GATE_FEATURE_NAMES",
    "RANKER_FEATURE_GROUPS",
    "RANKER_FEATURE_NAMES",
    "RankedDecision",
    "build_candidate_groups",
    "fit_nil_gate",
    "fit_ranker",
    "gate_scores",
    "model_summary",
    "out_of_fold_ranked_decisions",
    "rank_groups",
    "ranking_metrics",
    "select_risk_bounded_threshold",
    "threshold_predictions",
]
