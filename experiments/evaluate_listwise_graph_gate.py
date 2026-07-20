"""Evaluate a S2AND-inspired open-set gate on Project Two graph proposals.

The protocol is deliberately temporal and frozen: 2021 fits coefficients,
2022 selects a feature family and threshold, and 2023+ is opened once for the
confirmatory comparison.  Mention-level names and identity labels never enter
the output artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
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
        "listwise_no_topic": BASE_FEATURE_GROUPS["listwise"],
    }
    if not with_topic:
        return groups
    topic = tuple(range(len(FEATURE_NAMES), len(FEATURE_NAMES) + len(TopicProfileIndex.FEATURE_NAMES)))
    groups.update({
        "graph_topic": groups["graph_only"] + topic,
        "pointwise_topic": groups["pointwise"] + topic,
        "listwise_topic": groups["listwise_no_topic"] + topic,
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
    output = []
    for position, (record, proposal) in enumerate(zip(records, native)):
        if record.get("decision") not in {"new", "unknown"}:
            continue
        proposal_id = str(proposal.get("prediction") or "")
        if not proposal_id:
            continue
        if (
            gate_after_native_threshold is not None
            and float(proposal.get("graph_support") or 0.0)
            >= gate_after_native_threshold
        ):
            continue
        paper_key = str(record.get("article_id") or position)
        base_features = graph_proposal_features(
            record,
            proposal,
            profile_size=int(replay["profile_sizes"].get(proposal_id, 0)),
            paper_size=paper_sizes[paper_key],
            fixed_merge_count=fixed_by_paper[paper_key],
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
) -> list[str | None]:
    output: list[str | None] = []
    for position, (record, proposal) in enumerate(zip(
        replay["project2"]["records"], replay["native"]
    )):
        prediction = (
            str(record.get("author_id") or "")
            if record.get("decision") == "merge"
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
) -> dict[str, Any]:
    records = replay["project2"]["records"]
    new_mentions = sum(not bool(record.get("gold_seen_in_history")) for record in records)
    max_unseen_false = math.floor(new_mentions * max_unseen_false_rate)
    max_score = max(scores.values(), default=0.0)
    thresholds = [math.nextafter(max_score, math.inf), *sorted(set(scores.values()), reverse=True)]
    best: tuple[int, int, int, float, list[str | None]] | None = None
    for threshold in thresholds:
        accepted = [
            example
            for example in examples
            if scores[int(example["position"])] >= threshold
        ]
        correct = sum(bool(example["correct"]) for example in accepted)
        wrong_known = sum(
            bool(example["known"] and not example["correct"])
            for example in accepted
        )
        unseen_false = sum(not bool(example["known"]) for example in accepted)
        if unseen_false > max_unseen_false or wrong_known > max_wrong_known:
            continue
        predictions = combined_predictions(
            replay,
            scores,
            threshold,
            preserve_native_threshold=preserve_native_threshold,
        )
        candidate = (correct, -(wrong_known + unseen_false), -len(accepted), threshold, predictions)
        if best is None or candidate[:4] > best[:4]:
            best = candidate
    if best is None:
        raise ValueError("no listwise threshold satisfies the validation risk budget")
    accepted = [
        example
        for example in examples
        if scores[int(example["position"])] >= best[3]
    ]
    return {
        "threshold": best[3],
        "max_unseen_false_rate": max_unseen_false_rate,
        "max_unseen_false": max_unseen_false,
        "max_wrong_known": max_wrong_known,
        "accepted_proposals": len(accepted),
        "correct_rescues": sum(bool(example["correct"]) for example in accepted),
        "wrong_known_rescues": sum(
            bool(example["known"] and not example["correct"])
            for example in accepted
        ),
        "unseen_false_links": sum(not bool(example["known"]) for example in accepted),
        "combined": prediction_counts(records, best[4]),
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
    parser.add_argument("--max-unseen-false-rate", type=float, default=0.001)
    parser.add_argument("--max-wrong-known", type=int, default=1)
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

    # The confirmatory partition is not constructed until model family and
    # threshold have been selected from the validation year.
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
    )
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
            },
            "test": {
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
            "selection_rule": (
                "maximize correct validation rescues under unseen/wrong-link budgets; "
                "then prefer fewer errors and fewer features"
            ),
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
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
