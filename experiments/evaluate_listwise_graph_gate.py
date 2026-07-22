"""Evaluate a S2AND-inspired open-set gate on Project Two graph proposals.

The protocol is deliberately temporal and frozen: 2021 fits coefficients,
2022 selects a feature family and threshold, and 2023+ is opened once for the
confirmatory comparison.  Mention-level names and identity labels never enter
the output artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.listwise_open_set_gate import (  # noqa: E402
    FEATURE_GROUPS as BASE_FEATURE_GROUPS,
    FEATURE_NAMES,
    graph_proposal_features,
)
from disambiguation_engine.paper_graph_rescue import HistoricalCoauthorGraph  # noqa: E402
from disambiguation_engine.topic_profile_evidence import TopicProfileIndex  # noqa: E402
from evaluation.risk_bounds import chernoff_kl_upper_bound  # noqa: E402
from experiments.compare_core_with_istina_proxy import (  # noqa: E402
    ablate_project2_evidence,
    apply_fallback_predictions,
    build_proxy_mentions,
    evaluate_proxy,
    frozen_history_cluster_metrics,
    load_project1_proxy,
    load_real_structured_rows,
    native_graph_records,
    paper_coauthor_names,
    project2_config,
    sha256_file,
    split_positions,
    to_project2_mention,
    wilson_interval_95,
)
from experiments.istina_runtime_replay import evaluate, exact_mcnemar_two_sided  # noqa: E402
from experiments.train_calibrated_candidate_model import (  # noqa: E402
    fit_logistic,
    probability,
)
from integrations.istina_pipeline import IstinaDisambiguationPipeline  # noqa: E402


def peak_working_set_bytes() -> int | None:
    """Return the OS process peak without enabling high-overhead tracing."""

    try:
        import psutil

        memory = psutil.Process().memory_info()
        value = getattr(memory, "peak_wset", None)
        return int(value) if value is not None else None
    except (ImportError, OSError):
        return None


def load_crossref_work_metadata(path: Path) -> dict[str, dict[str, Any]]:
    """Load real Crossref work fields keyed by DOI; never copy author names."""

    output: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = row.get("message") or {}
            doi = str(row.get("doi") or message.get("DOI") or "").casefold()
            if not doi or not isinstance(message, Mapping):
                continue
            output[doi] = {
                "title": message.get("title") or (),
                "abstract": message.get("abstract") or "",
                "container-title": message.get("container-title") or (),
            }
    return output


def experiment_feature_groups(with_topic: bool) -> dict[str, tuple[int, ...]]:
    groups = {
        "graph_only": BASE_FEATURE_GROUPS["graph_only"],
        "pointwise": BASE_FEATURE_GROUPS["pointwise"],
        "listwise_no_cross_profile": BASE_FEATURE_GROUPS["listwise_no_cross_profile"],
        "listwise_cross_profile": BASE_FEATURE_GROUPS["listwise"],
    }
    if not with_topic:
        return groups
    topic = tuple(range(len(FEATURE_NAMES), len(FEATURE_NAMES) + len(TopicProfileIndex.FEATURE_NAMES)))
    groups.update({
        "graph_topic": groups["graph_only"] + topic,
        "pointwise_topic": groups["pointwise"] + topic,
        "listwise_no_cross_profile_topic": (
            groups["listwise_no_cross_profile"] + topic
        ),
        "listwise_cross_profile_topic": groups["listwise_cross_profile"] + topic,
    })
    return groups


def build_replay(
    mentions: list[Any],
    api: Mapping[str, Any],
    *,
    cutoff_year: int,
    test_from_year: int,
    test_through_year: int | None,
    calibrated_candidate_threshold: float,
) -> dict[str, Any]:
    history_positions, test_positions = split_positions(
        mentions,
        "temporal",
        cutoff_year,
        test_from_year,
        test_through_year,
    )
    replay = build_replay_from_positions(
        mentions,
        api,
        history_positions=history_positions,
        test_positions=test_positions,
        calibrated_candidate_threshold=calibrated_candidate_threshold,
    )
    replay.update({
        "cutoff_year": cutoff_year,
        "test_from_year": test_from_year,
        "test_through_year": test_through_year,
    })
    return replay


def build_replay_from_positions(
    mentions: list[Any],
    api: Mapping[str, Any],
    *,
    history_positions: Sequence[int],
    test_positions: Sequence[int],
    calibrated_candidate_threshold: float,
    include_proxy: bool = True,
) -> dict[str, Any]:
    proxy, proxy_records = (
        evaluate_proxy(mentions, list(history_positions), list(test_positions), api)
        if include_proxy else ({}, [])
    )
    coauthors = paper_coauthor_names(mentions)
    history = [
        to_project2_mention(mentions[position], position, position + 1, coauthors)
        for position in history_positions
    ]
    test = [
        to_project2_mention(mentions[position], position, position + 1, coauthors)
        for position in test_positions
    ]
    history = ablate_project2_evidence(history, "affiliation")
    test = ablate_project2_evidence(test, "affiliation")
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=project2_config(
            enable_calibrated_candidate_rescue=True,
            calibrated_candidate_threshold=calibrated_candidate_threshold,
        ),
        index_aliases=True,
    )
    project2 = evaluate(pipeline, test, {})
    native = native_graph_records(
        history,
        project2["records"],
        test,
        test_positions,
        pipeline.history_state.repair_profiles,
    )
    return {
        "history_mentions": len(history),
        "test_mentions": len(test),
        "project2": project2,
        "native": native,
        "proxy": proxy,
        "proxy_records": proxy_records,
        "profile_sizes": HistoricalCoauthorGraph.from_mentions(history).profile_sizes,
        "history_mentions_raw": history,
        "test_mentions_raw": test,
    }


def validation_selection_and_certification_positions(
    mentions: Sequence[Any],
    *,
    history_through_year: int,
    validation_year: int,
    certification_modulus: int,
) -> tuple[list[int], list[int], list[int]]:
    """Split one validation year by paper before constructing either replay.

    One hash bucket is reserved for certification.  Consequently every author
    mention from the same paper stays on the same side, and the threshold
    selected on the remaining papers cannot adapt to certification outcomes.
    """

    if certification_modulus < 2:
        raise ValueError("certification_modulus must be at least two")
    history = [
        position
        for position, mention in enumerate(mentions)
        if mention.year is not None and mention.year <= history_through_year
    ]
    validation = [
        position
        for position, mention in enumerate(mentions)
        if mention.year is not None
        and mention.year > history_through_year
        and mention.year == validation_year
    ]

    def held_out(paper_key: str) -> bool:
        digest = hashlib.sha256(paper_key.casefold().encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % certification_modulus == 0

    selection = [
        position
        for position in validation
        if not held_out(str(mentions[position].paper_key))
    ]
    certification = [
        position
        for position in validation
        if held_out(str(mentions[position].paper_key))
    ]
    if not selection or not certification:
        raise ValueError(
            "paper-group validation split produced an empty selection or "
            "certification partition"
        )
    return history, selection, certification


def fixed_decision_risk_certificate(
    replay: Mapping[str, Any],
    predictions: Sequence[str | None],
    *,
    confidence: float,
    max_unseen_false_rate: float,
    max_wrong_known_rate: float,
) -> dict[str, Any]:
    """Certify the final combined decisions on an untouched paper split."""

    if len(predictions) != len(replay["project2"]["records"]):
        raise ValueError("predictions must align with certification records")
    if not 0.0 <= max_unseen_false_rate <= 1.0:
        raise ValueError("max_unseen_false_rate must be in [0, 1]")
    if not 0.0 <= max_wrong_known_rate <= 1.0:
        raise ValueError("max_wrong_known_rate must be in [0, 1]")
    summary = prediction_counts(replay["project2"]["records"], predictions)
    counts = summary["counts"]
    unseen_upper = chernoff_kl_upper_bound(
        counts["false_links_new"], counts["new"], confidence=confidence
    )
    wrong_known_upper = chernoff_kl_upper_bound(
        counts["wrong_known"], counts["known"], confidence=confidence
    )
    unseen_passed = unseen_upper <= max_unseen_false_rate
    known_passed = wrong_known_upper <= max_wrong_known_rate
    return {
        "method": "one_sided_chernoff_binary_kl",
        "confidence": confidence,
        "threshold_fixed_before_certification": True,
        "unseen_false_link": {
            "events": counts["false_links_new"],
            "trials": counts["new"],
            "observed_rate": summary["metrics"]["new_author_false_link_rate"],
            "upper_bound": unseen_upper,
            "target": max_unseen_false_rate,
            "passed": unseen_passed,
        },
        "wrong_known_link": {
            "events": counts["wrong_known"],
            "trials": counts["known"],
            "observed_rate": (
                counts["wrong_known"] / counts["known"] if counts["known"] else 0.0
            ),
            "upper_bound": wrong_known_upper,
            "target": max_wrong_known_rate,
            "passed": known_passed,
        },
        "eligible_for_promotion": unseen_passed and known_passed,
    }


def paper_fold_training_replays(
    mentions: list[Any],
    api: Mapping[str, Any],
    *,
    through_year: int,
    folds: int,
    calibrated_candidate_threshold: float,
) -> list[dict[str, Any]]:
    """Build deterministic paper-group folds from historical labeled data."""

    if folds < 2:
        raise ValueError("paper-group training needs at least two folds")
    eligible = [
        position
        for position, mention in enumerate(mentions)
        if mention.year is not None and mention.year <= through_year
    ]
    papers = sorted({mentions[position].paper_key for position in eligible})
    fold_by_paper = {paper: index % folds for index, paper in enumerate(papers)}
    output = []
    for fold in range(folds):
        test_positions = [
            position
            for position in eligible
            if fold_by_paper[mentions[position].paper_key] == fold
        ]
        history_positions = [
            position
            for position in eligible
            if fold_by_paper[mentions[position].paper_key] != fold
        ]
        output.append(build_replay_from_positions(
            mentions,
            api,
            history_positions=history_positions,
            test_positions=test_positions,
            calibrated_candidate_threshold=calibrated_candidate_threshold,
            include_proxy=False,
        ))
    return output


def proposal_examples(
    replay: Mapping[str, Any],
    *,
    topic_index: TopicProfileIndex | None = None,
    metadata_by_paper: Mapping[str, Mapping[str, Any]] | None = None,
    gate_after_native_threshold: float | None = None,
    gate_base_merges: bool = False,
) -> list[dict[str, Any]]:
    records = list(replay["project2"]["records"])
    native = list(replay["native"])
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
            str(name) for name in mention.get("coauthors") or () if str(name).strip()
        )
    query_mentions = list(replay.get("test_mentions_raw") or ())
    output = []
    for position, (record, proposal) in enumerate(zip(records, native)):
        base_merge = record.get("decision") == "merge"
        if base_merge and not gate_base_merges:
            continue
        if not base_merge and record.get("decision") not in {"new", "unknown"}:
            continue
        effective_proposal = (
            {
                "prediction": record.get("author_id"),
                "graph_support": 0.0,
                "candidate_count": record.get("candidate_count"),
            }
            if base_merge else proposal
        )
        proposal_id = str(effective_proposal.get("prediction") or "")
        if not proposal_id:
            continue
        if (
            not base_merge
            and gate_after_native_threshold is not None
            and float(effective_proposal.get("graph_support") or 0.0)
            >= gate_after_native_threshold
        ):
            continue
        paper_key = str(record.get("article_id") or position)
        query_mention = query_mentions[position] if position < len(query_mentions) else {}
        base_features = graph_proposal_features(
            record,
            effective_proposal,
            profile_size=int(replay["profile_sizes"].get(proposal_id, 0)),
            paper_size=paper_sizes[paper_key],
            fixed_merge_count=fixed_by_paper[paper_key],
            query_year=query_mention.get("year"),
            profile_years=profile_years.get(proposal_id, ()),
            query_coauthors=query_mention.get("coauthors") or (),
            profile_coauthors=profile_coauthors.get(proposal_id, ()),
        )
        topic_features: tuple[float, ...] = ()
        if topic_index is not None and metadata_by_paper is not None:
            topic_features = topic_index.evidence(
                proposal_id,
                metadata_by_paper.get(paper_key.casefold(), {}),
            ).as_tuple()
        output.append({
            "position": position,
            "known": bool(record.get("gold_seen_in_history")),
            "correct": bool(
                record.get("gold_seen_in_history")
                and proposal_id == str(record.get("gold_author_id") or "")
            ),
            "source": "base_merge" if base_merge else "graph_proposal",
            "features": base_features + topic_features,
        })
    return output


def fit_group(
    examples: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
    *,
    l2: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.asarray([
        tuple(float(example["features"][index]) for index in indices)
        for example in examples
    ], dtype=float)
    labels = np.asarray([float(example["correct"]) for example in examples])
    if not labels.any() or labels.all():
        raise ValueError("training proposals need both positive and negative labels")
    # S2AND's released incremental gate assigns higher cost to false links and
    # wrong-candidate links than to abstention.  These are risk scores; the
    # acceptance threshold is calibrated separately on the validation year.
    weights = np.asarray([
        0.25 if example["correct"] else 1.5 if example["known"] else 1.0
        for example in examples
    ], dtype=float)
    return fit_logistic(features, labels, weights, l2=l2, iterations=75)


def score_examples(
    examples: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
    model: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> dict[int, float]:
    mean, scale, coefficients = model
    return {
        int(example["position"]): probability(
            tuple(float(example["features"][index]) for index in indices),
            mean,
            scale,
            coefficients,
        )
        for example in examples
    }


def combined_predictions(
    replay: Mapping[str, Any],
    scores: Mapping[int, float],
    threshold: float,
    preserve_native_threshold: float | None = None,
    gate_base_merges: bool = False,
) -> list[str | None]:
    output: list[str | None] = []
    for position, (record, proposal) in enumerate(zip(
        replay["project2"]["records"], replay["native"]
    )):
        base_prediction = (
            str(record.get("author_id") or "")
            if record.get("decision") == "merge"
            else ""
        )
        prediction = (
            base_prediction
            if base_prediction
            and (
                not gate_base_merges
                or float(scores.get(position, -1.0)) >= threshold
            )
            else ""
        )
        if (
            not prediction
            and proposal.get("prediction")
            and (
                (
                    preserve_native_threshold is not None
                    and float(proposal.get("graph_support") or 0.0)
                    >= preserve_native_threshold
                )
                or float(scores.get(position, -1.0)) >= threshold
            )
        ):
            prediction = str(proposal["prediction"])
        output.append(prediction or None)
    return output


def prediction_counts(
    records: Sequence[Mapping[str, Any]],
    predictions: Sequence[str | None],
) -> dict[str, Any]:
    counts = Counter(
        total=0,
        known=0,
        new=0,
        merges=0,
        correct_known=0,
        wrong_known=0,
        false_links_new=0,
    )
    for record, prediction in zip(records, predictions):
        known = bool(record.get("gold_seen_in_history"))
        truth = str(record.get("gold_author_id") or "")
        counts["total"] += 1
        counts["known" if known else "new"] += 1
        counts["merges"] += int(prediction is not None)
        counts["correct_known"] += int(known and prediction == truth)
        counts["wrong_known"] += int(
            known and prediction is not None and prediction != truth
        )
        counts["false_links_new"] += int(not known and prediction is not None)
    known_predictions = counts["correct_known"] + counts["wrong_known"]
    return {
        "counts": dict(counts),
        "metrics": {
            "known_recall": counts["correct_known"] / counts["known"] if counts["known"] else 0.0,
            "known_prediction_precision": counts["correct_known"] / known_predictions if known_predictions else 0.0,
            "all_link_precision": counts["correct_known"] / counts["merges"] if counts["merges"] else 0.0,
            "new_author_false_link_rate": counts["false_links_new"] / counts["new"] if counts["new"] else 0.0,
        },
    }


def choose_threshold(
    replay: Mapping[str, Any],
    examples: Sequence[Mapping[str, Any]],
    scores: Mapping[int, float],
    *,
    max_unseen_false_rate: float,
    max_wrong_known: int,
    preserve_native_threshold: float | None = None,
    gate_base_merges: bool = False,
    risk_confidence: float | None = None,
    max_wrong_known_rate: float | None = None,
) -> dict[str, Any]:
    records = replay["project2"]["records"]
    new_mentions = sum(not bool(record.get("gold_seen_in_history")) for record in records)
    known_mentions = len(records) - new_mentions
    if risk_confidence is not None and not gate_base_merges:
        raise ValueError("finite-sample selection must gate the full combined system")
    if risk_confidence is not None and max_wrong_known_rate is None:
        raise ValueError("max_wrong_known_rate is required for risk-bounded selection")
    max_unseen_false = math.floor(new_mentions * max_unseen_false_rate)
    ordered = sorted(
        examples,
        key=lambda example: scores[int(example["position"])],
        reverse=True,
    )
    max_score = scores[int(ordered[0]["position"])] if ordered else 0.0
    operating_points: list[tuple[float, int, int, int, int]] = [
        (math.nextafter(max_score, math.inf), 0, 0, 0, 0)
    ]
    accepted_count = correct = wrong_known = unseen_false = 0
    cursor = 0
    while cursor < len(ordered):
        threshold = scores[int(ordered[cursor]["position"])]
        while (
            cursor < len(ordered)
            and scores[int(ordered[cursor]["position"])] == threshold
        ):
            example = ordered[cursor]
            accepted_count += 1
            correct += int(bool(example["correct"]))
            wrong_known += int(bool(example["known"] and not example["correct"]))
            unseen_false += int(not bool(example["known"]))
            cursor += 1
        operating_points.append(
            (threshold, accepted_count, correct, wrong_known, unseen_false)
        )

    pointwise_confidence = (
        1.0 - (1.0 - risk_confidence) / len(operating_points)
        if risk_confidence is not None else None
    )

    best: tuple[int, int, int, float] | None = None
    for threshold, accepted_count, correct, wrong_known, unseen_false in operating_points:
        if risk_confidence is not None:
            unseen_upper = chernoff_kl_upper_bound(
                unseen_false, new_mentions, confidence=pointwise_confidence
            )
            wrong_known_upper = chernoff_kl_upper_bound(
                wrong_known, known_mentions, confidence=pointwise_confidence
            )
            if (
                unseen_upper > max_unseen_false_rate
                or wrong_known_upper > float(max_wrong_known_rate)
            ):
                continue
        elif unseen_false > max_unseen_false or wrong_known > max_wrong_known:
            continue
        candidate = (
            correct,
            -(wrong_known + unseen_false),
            -accepted_count,
            threshold,
        )
        if best is None or candidate > best:
            best = candidate
    if best is None:
        raise ValueError("no listwise threshold satisfies the validation risk budget")
    accepted = [
        example
        for example in examples
        if scores[int(example["position"])] >= best[3]
    ]
    predictions = combined_predictions(
        replay,
        scores,
        best[3],
        preserve_native_threshold=preserve_native_threshold,
        gate_base_merges=gate_base_merges,
    )
    selected_wrong_known = sum(
        bool(example["known"] and not example["correct"])
        for example in accepted
    )
    selected_unseen_false = sum(not bool(example["known"]) for example in accepted)
    selected_risk = (
        {
            "confidence": risk_confidence,
            "familywise_method": "bonferroni_over_threshold_operating_points",
            "operating_points": len(operating_points),
            "pointwise_confidence": pointwise_confidence,
            "unseen_false_link_upper_bound": chernoff_kl_upper_bound(
                selected_unseen_false,
                new_mentions,
                confidence=pointwise_confidence,
            ),
            "unseen_false_link_target": max_unseen_false_rate,
            "wrong_known_upper_bound": chernoff_kl_upper_bound(
                selected_wrong_known,
                known_mentions,
                confidence=pointwise_confidence,
            ),
            "wrong_known_target": max_wrong_known_rate,
        }
        if risk_confidence is not None else None
    )
    return {
        "threshold": best[3],
        "max_unseen_false_rate": max_unseen_false_rate,
        "max_unseen_false": max_unseen_false,
        "max_wrong_known": max_wrong_known,
        "accepted_proposals": len(accepted),
        "correct_rescues": sum(bool(example["correct"]) for example in accepted),
        "wrong_known_rescues": selected_wrong_known,
        "unseen_false_links": selected_unseen_false,
        "selection_risk_bound": selected_risk,
        "combined": prediction_counts(records, predictions),
    }


def base_predictions(replay: Mapping[str, Any]) -> list[str | None]:
    return [
        str(record.get("author_id") or "") or None
        if record.get("decision") == "merge"
        else None
        for record in replay["project2"]["records"]
    ]


def proxy_predictions(replay: Mapping[str, Any]) -> list[str | None]:
    return [
        str(record.get("prediction") or "") or None
        for record in replay["proxy_records"]
    ]


def native_predictions(replay: Mapping[str, Any]) -> list[str | None]:
    test_positions = [int(record["source_position"]) for record in replay["native"]]
    return apply_fallback_predictions(
        replay["native"],
        replay["project2"]["records"],
        test_positions,
        "unknown_or_new",
        0.5,
    )


def paired_binary(
    records: Sequence[Mapping[str, Any]],
    left: Sequence[str | None],
    right: Sequence[str | None],
    *,
    known: bool,
) -> dict[str, Any]:
    left_only = right_only = 0
    for record, left_prediction, right_prediction in zip(records, left, right):
        if bool(record.get("gold_seen_in_history")) != known:
            continue
        truth = str(record.get("gold_author_id") or "")
        if known:
            left_correct = left_prediction == truth
            right_correct = right_prediction == truth
        else:
            left_correct = left_prediction is None
            right_correct = right_prediction is None
        left_only += int(left_correct and not right_correct)
        right_only += int(right_correct and not left_correct)
    return {
        "left_only_correct": left_only,
        "right_only_correct": right_only,
        "mcnemar_exact_two_sided_p": exact_mcnemar_two_sided(left_only, right_only),
    }


def aggregate_method(
    replay: Mapping[str, Any],
    predictions: Sequence[str | None],
) -> dict[str, Any]:
    result = prediction_counts(replay["project2"]["records"], predictions)
    counts = result["counts"]
    result["confidence_intervals_95"] = {
        "known_recall": wilson_interval_95(counts["correct_known"], counts["known"]),
        "known_prediction_precision": wilson_interval_95(
            counts["correct_known"], counts["correct_known"] + counts["wrong_known"]
        ),
        "new_author_false_link_rate": wilson_interval_95(
            counts["false_links_new"], counts["new"]
        ),
    }
    result["clustering"] = frozen_history_cluster_metrics(
        replay["project2"]["records"], list(predictions)
    )
    return result


def model_artifact(
    indices: Sequence[int],
    all_feature_names: Sequence[str],
    model: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> dict[str, Any]:
    mean, scale, coefficients = model
    return {
        "feature_names": [all_feature_names[index] for index in indices],
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "intercept": float(coefficients[0]),
        "coefficients": coefficients[1:].tolist(),
    }


def main() -> int:
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--crossref-raw", type=Path)
    parser.add_argument("--project1-root", type=Path, required=True)
    parser.add_argument("--train-history-cutoff", type=int, default=2020)
    parser.add_argument("--train-year", type=int, default=2021)
    parser.add_argument(
        "--train-paper-folds",
        type=int,
        default=0,
        help="Use leakage-safe paper-group folds through the evaluation history cutoff.",
    )
    parser.add_argument("--evaluation-history-cutoff", type=int, default=2021)
    parser.add_argument("--validation-year", type=int, default=2022)
    parser.add_argument("--test-from-year", type=int, default=2023)
    parser.add_argument("--l2", type=float, default=2.0)
    parser.add_argument("--calibrated-candidate-threshold", type=float, default=0.995)
    parser.add_argument(
        "--preserve-native-threshold",
        type=float,
        help="Keep graph proposals at or above this support, and gate only the residual.",
    )
    parser.add_argument(
        "--gate-base-merges",
        action="store_true",
        help="Apply the learned selective gate to base MERGE decisions too.",
    )
    parser.add_argument("--max-unseen-false-rate", type=float, default=0.001)
    parser.add_argument("--max-wrong-known", type=int, default=1)
    parser.add_argument(
        "--selection-risk-confidence",
        type=float,
        help="Use a one-sided finite-sample risk bound during threshold selection.",
    )
    parser.add_argument(
        "--selection-max-wrong-known-rate",
        type=float,
        default=0.01,
    )
    parser.add_argument(
        "--validation-certification-modulus",
        type=int,
        default=0,
        help=(
            "Reserve one deterministic paper-hash bucket out of this many "
            "validation buckets for independent risk certification (0 disables)."
        ),
    )
    parser.add_argument(
        "--certification-status",
        choices=("opened_development", "independent_frozen"),
        default="opened_development",
        help=(
            "Mark whether certification labels were untouched for this exact "
            "frozen method. The safe default cannot authorize promotion."
        ),
    )
    parser.add_argument("--risk-confidence", type=float, default=0.95)
    parser.add_argument(
        "--certificate-max-unseen-false-rate", type=float, default=0.005
    )
    parser.add_argument(
        "--certificate-max-wrong-known-rate", type=float, default=0.01
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = load_real_structured_rows(args.dataset)
    metadata_by_paper = (
        load_crossref_work_metadata(args.crossref_raw)
        if args.crossref_raw else None
    )
    groups = experiment_feature_groups(metadata_by_paper is not None)
    all_feature_names = FEATURE_NAMES + (
        TopicProfileIndex.FEATURE_NAMES if metadata_by_paper is not None else ()
    )
    api = load_project1_proxy(args.project1_root)
    mentions = build_proxy_mentions(rows, api["row_to_mention"])
    certification = None
    if args.validation_certification_modulus:
        history_positions, selection_positions, certification_positions = (
            validation_selection_and_certification_positions(
                mentions,
                history_through_year=args.evaluation_history_cutoff,
                validation_year=args.validation_year,
                certification_modulus=args.validation_certification_modulus,
            )
        )
        validation = build_replay_from_positions(
            mentions,
            api,
            history_positions=history_positions,
            test_positions=selection_positions,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
            include_proxy=False,
        )
        certification = build_replay_from_positions(
            mentions,
            api,
            history_positions=history_positions,
            test_positions=certification_positions,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
            include_proxy=False,
        )
    else:
        validation = build_replay(
            mentions,
            api,
            cutoff_year=args.evaluation_history_cutoff,
            test_from_year=args.validation_year,
            test_through_year=args.validation_year,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        )
    validation_topic = (
        TopicProfileIndex.from_history(
            validation["history_mentions_raw"], metadata_by_paper
        ) if metadata_by_paper is not None else None
    )
    if args.train_paper_folds:
        train_replays = paper_fold_training_replays(
            mentions,
            api,
            through_year=args.evaluation_history_cutoff,
            folds=args.train_paper_folds,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        )
        train_examples = []
        for replay in train_replays:
            topic_index = (
                TopicProfileIndex.from_history(
                    replay["history_mentions_raw"], metadata_by_paper
                ) if metadata_by_paper is not None else None
            )
            train_examples.extend(proposal_examples(
                replay,
                topic_index=topic_index,
                metadata_by_paper=metadata_by_paper,
                gate_after_native_threshold=args.preserve_native_threshold,
                gate_base_merges=args.gate_base_merges,
            ))
        train_protocol = {
            "strategy": "deterministic_paper_group_folds",
            "source_through_year": args.evaluation_history_cutoff,
            "folds": args.train_paper_folds,
            "fold_history_mentions": [
                replay["history_mentions"] for replay in train_replays
            ],
            "fold_query_mentions": [
                replay["test_mentions"] for replay in train_replays
            ],
        }
    else:
        train = build_replay(
            mentions,
            api,
            cutoff_year=args.train_history_cutoff,
            test_from_year=args.train_year,
            test_through_year=args.train_year,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        )
        train_topic = (
            TopicProfileIndex.from_history(
                train["history_mentions_raw"], metadata_by_paper
            ) if metadata_by_paper is not None else None
        )
        train_examples = proposal_examples(
            train,
            topic_index=train_topic,
            metadata_by_paper=metadata_by_paper,
            gate_after_native_threshold=args.preserve_native_threshold,
            gate_base_merges=args.gate_base_merges,
        )
        train_protocol = {
            "strategy": "temporal",
            "history_through": args.train_history_cutoff,
            "query_year": args.train_year,
            "history_mentions": train["history_mentions"],
            "query_mentions": train["test_mentions"],
        }
    validation_examples = proposal_examples(
        validation,
        topic_index=validation_topic,
        metadata_by_paper=metadata_by_paper,
        gate_after_native_threshold=args.preserve_native_threshold,
        gate_base_merges=args.gate_base_merges,
    )

    candidates: dict[str, Any] = {}
    fitted: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for group, indices in groups.items():
        model = fit_group(train_examples, indices, l2=args.l2)
        fitted[group] = model
        validation_scores = score_examples(validation_examples, indices, model)
        selection = choose_threshold(
            validation,
            validation_examples,
            validation_scores,
            max_unseen_false_rate=args.max_unseen_false_rate,
            max_wrong_known=args.max_wrong_known,
            preserve_native_threshold=args.preserve_native_threshold,
            gate_base_merges=args.gate_base_merges,
            risk_confidence=args.selection_risk_confidence,
            max_wrong_known_rate=args.selection_max_wrong_known_rate,
        )
        candidates[group] = {
            **selection,
            "feature_count": len(indices),
        }

    selected_group = max(
        groups,
        key=lambda group: (
            candidates[group]["correct_rescues"],
            -candidates[group]["wrong_known_rescues"],
            -candidates[group]["unseen_false_links"],
            -len(groups[group]),
        ),
    )
    threshold = float(candidates[selected_group]["threshold"])

    risk_certificate = None
    if certification is not None:
        certification_topic = (
            TopicProfileIndex.from_history(
                certification["history_mentions_raw"], metadata_by_paper
            ) if metadata_by_paper is not None else None
        )
        certification_examples = proposal_examples(
            certification,
            topic_index=certification_topic,
            metadata_by_paper=metadata_by_paper,
            gate_after_native_threshold=args.preserve_native_threshold,
            gate_base_merges=args.gate_base_merges,
        )
        certification_scores = score_examples(
            certification_examples,
            groups[selected_group],
            fitted[selected_group],
        )
        certification_predictions = combined_predictions(
            certification,
            certification_scores,
            threshold,
            preserve_native_threshold=args.preserve_native_threshold,
            gate_base_merges=args.gate_base_merges,
        )
        risk_certificate = fixed_decision_risk_certificate(
            certification,
            certification_predictions,
            confidence=args.risk_confidence,
            max_unseen_false_rate=args.certificate_max_unseen_false_rate,
            max_wrong_known_rate=args.certificate_max_wrong_known_rate,
        )
        risk_certificate["statistical_risk_passed"] = risk_certificate[
            "eligible_for_promotion"
        ]
        risk_certificate["label_status"] = args.certification_status
        risk_certificate["eligible_for_promotion"] = bool(
            risk_certificate["statistical_risk_passed"]
            and args.certification_status == "independent_frozen"
        )
        risk_certificate["comparators"] = {
            "project2_base": fixed_decision_risk_certificate(
                certification,
                base_predictions(certification),
                confidence=args.risk_confidence,
                max_unseen_false_rate=args.certificate_max_unseen_false_rate,
                max_wrong_known_rate=args.certificate_max_wrong_known_rate,
            ),
            "native_graph_threshold_0_5": fixed_decision_risk_certificate(
                certification,
                native_predictions(certification),
                confidence=args.risk_confidence,
                max_unseen_false_rate=args.certificate_max_unseen_false_rate,
                max_wrong_known_rate=args.certificate_max_wrong_known_rate,
            ),
        }

    # The confirmatory partition is not constructed until model family and
    # threshold have been selected from the validation year.
    test_phase_started = time.perf_counter()
    test = build_replay(
        mentions,
        api,
        cutoff_year=args.evaluation_history_cutoff,
        test_from_year=args.test_from_year,
        test_through_year=None,
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
    )
    test_topic = (
        TopicProfileIndex.from_history(test["history_mentions_raw"], metadata_by_paper)
        if metadata_by_paper is not None else None
    )
    test_examples = proposal_examples(
        test,
        topic_index=test_topic,
        metadata_by_paper=metadata_by_paper,
        gate_after_native_threshold=args.preserve_native_threshold,
        gate_base_merges=args.gate_base_merges,
    )
    test_scores = score_examples(
        test_examples,
        groups[selected_group],
        fitted[selected_group],
    )
    selected_predictions = combined_predictions(
        test,
        test_scores,
        threshold,
        preserve_native_threshold=args.preserve_native_threshold,
        gate_base_merges=args.gate_base_merges,
    )
    test_phase_wall_seconds = time.perf_counter() - test_phase_started
    base = base_predictions(test)
    native = native_predictions(test)
    proxy = proxy_predictions(test)
    records = test["project2"]["records"]

    report = {
        "protocol": {
            "dataset_sha256": sha256_file(args.dataset),
            "real_crossref_given_family_fields_only": True,
            "orcid_used_as_label_only": True,
            "original_name_removed_and_asserted_empty": True,
            "affiliation_ablated": True,
            "frozen_calibrated_candidate_threshold": args.calibrated_candidate_threshold,
            "preserved_native_graph_threshold": args.preserve_native_threshold,
            "selective_veto_of_base_merges": args.gate_base_merges,
            "crossref_title_abstract_venue_features": metadata_by_paper is not None,
            "crossref_raw_sha256": (
                sha256_file(args.crossref_raw) if args.crossref_raw else None
            ),
            "mention_level_data_emitted": False,
            "train": train_protocol,
            "validation": {
                "history_through": args.evaluation_history_cutoff,
                "query_year": args.validation_year,
                "history_mentions": validation["history_mentions"],
                "query_mentions": validation["test_mentions"],
                "selection_query_mentions": validation["test_mentions"],
                "certification_query_mentions": (
                    certification["test_mentions"] if certification is not None else 0
                ),
                "certification_paper_hash_modulus": (
                    args.validation_certification_modulus or None
                ),
                "certification_label_status": args.certification_status,
            },
            "test": {
                "role": "development_transfer_benchmark",
                "final_claim_eligible": False,
                "history_through": args.evaluation_history_cutoff,
                "query_from_year": args.test_from_year,
                "history_mentions": test["history_mentions"],
                "query_mentions": test["test_mentions"],
            },
            "risk_costs": {
                "false_abstain": 0.25,
                "unseen_false_link": 1.0,
                "wrong_candidate_link": 1.5,
            },
            "validation_risk_bound": {
                "confidence": args.selection_risk_confidence,
                "max_unseen_false_rate": args.max_unseen_false_rate,
                "max_wrong_known_rate": args.selection_max_wrong_known_rate,
            },
            "selection_rule": (
                "maximize correct validation rescues under unseen/wrong-link budgets; "
                "then prefer fewer errors and fewer features"
            ),
            "complexity_contract": {
                "notation": {
                    "H": "history mentions",
                    "C": "retrieved candidates per query (capped)",
                    "K": "retained top candidates",
                    "A": "authors on one incoming paper",
                    "B": "paper-graph beam width",
                    "D": "gate feature count",
                },
                "history_index_time": "O(H + sum_over_papers(authors_on_paper^2))",
                "candidate_lookup_time": "O(sum_posting_lengths + C log C)",
                "candidate_scoring_time_per_query": "O(C)",
                "paper_graph_time_per_paper": "O(B * C * A^2)",
                "cross_profile_gate_time_per_query": "O(K + profile_years + profile_coauthors)",
                "gate_scoring_time_per_query": "O(D)",
                "online_space": "O(H + graph_edges + B*A + C)",
                "hard_caps": {
                    "candidate_pool": 100,
                    "topk": 20,
                    "paper_graph_beam": 256,
                },
            },
        },
        "training": {
            "proposal_examples": len(train_examples),
            "correct_known_proposals": sum(bool(row["correct"]) for row in train_examples),
            "wrong_known_proposals": sum(
                bool(row["known"] and not row["correct"]) for row in train_examples
            ),
            "unseen_proposals": sum(not bool(row["known"]) for row in train_examples),
            "l2": args.l2,
        },
        "validation_feature_ablation": candidates,
        "selected_model": {
            "feature_group": selected_group,
            "threshold": threshold,
            **model_artifact(
                groups[selected_group],
                all_feature_names,
                fitted[selected_group],
            ),
        },
        "independent_risk_certificate": risk_certificate,
        "test": {
            "istina_hypergraph_proxy": aggregate_method(test, proxy),
            "project2_base": aggregate_method(test, base),
            "project2_native_graph_threshold_0_5": aggregate_method(test, native),
            "project2_selected_open_set_gate": aggregate_method(
                test, selected_predictions
            ),
            "paired_known": {
                "gate_vs_base": paired_binary(records, selected_predictions, base, known=True),
                "gate_vs_native_graph": paired_binary(records, selected_predictions, native, known=True),
                "gate_vs_istina_proxy": paired_binary(records, selected_predictions, proxy, known=True),
            },
            "paired_unseen_safe_rejection": {
                "gate_vs_base": paired_binary(records, selected_predictions, base, known=False),
                "gate_vs_native_graph": paired_binary(records, selected_predictions, native, known=False),
                "gate_vs_istina_proxy": paired_binary(records, selected_predictions, proxy, known=False),
            },
        },
        "limitations": [
            "The ISTINA baseline is a frozen source-faithful Python proxy, not the compiled service.",
            "ORCID labels are known to be a demographically and temporally biased sample.",
            "Independent ISTINA person-ID labels are still required for an ISTINA superiority claim.",
            "The gate is a lightweight logistic reproduction of listwise risk features, not S2AND's released LightGBM model.",
            "The finite-sample certificate assumes the held-out paper-group decisions are representative Bernoulli risk observations; ISTINA transfer still requires an independent certificate.",
        ],
    }
    report["runtime"] = {
        "wall_seconds": time.perf_counter() - wall_started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_working_set_bytes": peak_working_set_bytes(),
        "development_transfer_phase_wall_seconds": test_phase_wall_seconds,
        "development_transfer_queries": test["test_mentions"],
        "development_transfer_queries_per_second": (
            test["test_mentions"] / test_phase_wall_seconds
            if test_phase_wall_seconds else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "report": str(args.output),
        "selected_feature_group": selected_group,
        "feature_count": len(groups[selected_group]),
        "risk_certificate_passed": (
            risk_certificate.get("eligible_for_promotion")
            if risk_certificate is not None else None
        ),
        "development_transfer_queries": test["test_mentions"],
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
