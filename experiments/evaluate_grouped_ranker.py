"""Evaluate a compact group ranker plus explicit NIL gate on public data.

This is an offline research experiment.  It keeps Project Two candidate
retrieval fixed, fits the NIL gate from out-of-fold ranker decisions, emits
aggregate evidence only, and treats 2023+ as a development/transfer benchmark.
"""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.compare_core_with_istina_proxy import (  # noqa: E402
    build_proxy_mentions,
    load_project1_proxy,
    load_real_structured_rows,
    sha256_file,
)
from experiments.evaluate_listwise_graph_gate import (  # noqa: E402
    aggregate_method,
    base_predictions,
    build_replay,
    build_replay_from_positions,
    fixed_decision_risk_certificate,
    native_predictions,
    paired_binary,
    peak_working_set_bytes,
    proxy_predictions,
    validation_selection_and_certification_positions,
)
from experiments.grouped_candidate_ranker import (  # noqa: E402
    GATE_FEATURE_NAMES,
    RANKER_FEATURE_GROUPS,
    RANKER_FEATURE_NAMES,
    build_candidate_groups,
    fit_nil_gate,
    fit_ranker,
    gate_scores,
    model_summary,
    out_of_fold_ranked_decisions,
    rank_groups,
    ranking_metrics,
    select_risk_bounded_threshold,
    threshold_predictions,
)


def _trial_counts(replay: dict[str, Any]) -> tuple[int, int]:
    records = replay["project2"]["records"]
    known = sum(bool(record.get("gold_seen_in_history")) for record in records)
    return known, len(records) - known


def _certify(
    replay: dict[str, Any],
    predictions: list[str | None],
    *,
    confidence: float,
    max_new_false_rate: float,
    max_wrong_known_rate: float,
    label_status: str,
) -> dict[str, Any]:
    certificate = fixed_decision_risk_certificate(
        replay,
        predictions,
        confidence=confidence,
        max_unseen_false_rate=max_new_false_rate,
        max_wrong_known_rate=max_wrong_known_rate,
    )
    certificate["statistical_risk_passed"] = certificate["eligible_for_promotion"]
    certificate["label_status"] = label_status
    certificate["eligible_for_promotion"] = bool(
        certificate["statistical_risk_passed"]
        and label_status == "independent_frozen"
    )
    return certificate


def main() -> int:
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--project1-root", type=Path, required=True)
    parser.add_argument("--train-history-cutoff", type=int, default=2020)
    parser.add_argument("--train-year", type=int, default=2021)
    parser.add_argument("--evaluation-history-cutoff", type=int, default=2021)
    parser.add_argument("--validation-year", type=int, default=2022)
    parser.add_argument("--test-from-year", type=int, default=2023)
    parser.add_argument("--validation-certification-modulus", type=int, default=5)
    parser.add_argument("--oof-folds", type=int, default=5)
    parser.add_argument(
        "--ranker-feature-group",
        choices=tuple(RANKER_FEATURE_GROUPS),
        default="listwise_cross_profile",
    )
    parser.add_argument("--selection-confidence", type=float, default=0.95)
    parser.add_argument("--max-new-false-rate", type=float, default=0.005)
    parser.add_argument("--max-wrong-known-rate", type=float, default=0.01)
    parser.add_argument(
        "--certification-status",
        choices=("opened_development", "independent_frozen"),
        default="opened_development",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = load_real_structured_rows(args.dataset)
    api = load_project1_proxy(args.project1_root)
    mentions = build_proxy_mentions(rows, api["row_to_mention"])
    del rows

    train = build_replay(
        mentions,
        api,
        cutoff_year=args.train_history_cutoff,
        test_from_year=args.train_year,
        test_through_year=args.train_year,
        calibrated_candidate_threshold=0.995,
    )
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
        calibrated_candidate_threshold=0.995,
        include_proxy=False,
    )
    certification = build_replay_from_positions(
        mentions,
        api,
        history_positions=history_positions,
        test_positions=certification_positions,
        calibrated_candidate_threshold=0.995,
        include_proxy=False,
    )

    feature_indices = RANKER_FEATURE_GROUPS[args.ranker_feature_group]
    ranker_feature_names = [RANKER_FEATURE_NAMES[index] for index in feature_indices]
    train_groups = build_candidate_groups(train)
    train_known, train_new = _trial_counts(train)
    oof_decisions = out_of_fold_ranked_decisions(
        train_groups,
        feature_indices,
        folds=args.oof_folds,
    )
    nil_gate = fit_nil_gate(oof_decisions)
    ranker = fit_ranker(train_groups, feature_indices)

    validation_groups = build_candidate_groups(validation)
    validation_decisions = rank_groups(ranker, validation_groups, feature_indices)
    validation_scores = gate_scores(nil_gate, validation_decisions)
    validation_known, validation_new = _trial_counts(validation)
    selection = select_risk_bounded_threshold(
        validation_decisions,
        validation_scores,
        known_trials=validation_known,
        new_trials=validation_new,
        confidence=args.selection_confidence,
        max_new_false_rate=args.max_new_false_rate,
        max_wrong_known_rate=args.max_wrong_known_rate,
    )
    threshold = float(selection["threshold"])

    certification_groups = build_candidate_groups(certification)
    certification_decisions = rank_groups(ranker, certification_groups, feature_indices)
    certification_scores = gate_scores(nil_gate, certification_decisions)
    certification_predictions = threshold_predictions(
        certification["test_mentions"],
        certification_decisions,
        certification_scores,
        threshold,
    )
    certificate = _certify(
        certification,
        certification_predictions,
        confidence=args.selection_confidence,
        max_new_false_rate=args.max_new_false_rate,
        max_wrong_known_rate=args.max_wrong_known_rate,
        label_status=args.certification_status,
    )
    certificate["comparators"] = {
        "project2_base": _certify(
            certification,
            base_predictions(certification),
            confidence=args.selection_confidence,
            max_new_false_rate=args.max_new_false_rate,
            max_wrong_known_rate=args.max_wrong_known_rate,
            label_status=args.certification_status,
        ),
        "native_graph_threshold_0_5": _certify(
            certification,
            native_predictions(certification),
            confidence=args.selection_confidence,
            max_new_false_rate=args.max_new_false_rate,
            max_wrong_known_rate=args.max_wrong_known_rate,
            label_status=args.certification_status,
        ),
    }

    training_summary = {
        "query_groups": len(train_groups),
        "oof_decisions": len(oof_decisions),
        "oof_folds": args.oof_folds,
        "known_candidate_coverage": ranking_metrics(
            train_groups,
            oof_decisions,
            known_trials=train_known,
            new_trials=train_new,
        ),
    }
    validation_summary = {
        "ranking": ranking_metrics(
            validation_groups,
            validation_decisions,
            known_trials=validation_known,
            new_trials=validation_new,
        ),
        "threshold_selection": selection,
    }
    certification_known, certification_new = _trial_counts(certification)
    certification_summary = {
        "ranking": ranking_metrics(
            certification_groups,
            certification_decisions,
            known_trials=certification_known,
            new_trials=certification_new,
        ),
        "risk": certificate,
    }

    del train, train_groups, oof_decisions, validation_groups, validation_decisions
    del certification_groups, certification_decisions
    gc.collect()

    transfer_started = time.perf_counter()
    transfer = build_replay(
        mentions,
        api,
        cutoff_year=args.evaluation_history_cutoff,
        test_from_year=args.test_from_year,
        test_through_year=None,
        calibrated_candidate_threshold=0.995,
    )
    transfer_groups = build_candidate_groups(transfer)
    transfer_decisions = rank_groups(ranker, transfer_groups, feature_indices)
    transfer_scores = gate_scores(nil_gate, transfer_decisions)
    selected_predictions = threshold_predictions(
        transfer["test_mentions"],
        transfer_decisions,
        transfer_scores,
        threshold,
    )
    transfer_wall = time.perf_counter() - transfer_started
    base = base_predictions(transfer)
    native = native_predictions(transfer)
    proxy = proxy_predictions(transfer)
    records = transfer["project2"]["records"]
    transfer_known, transfer_new = _trial_counts(transfer)

    report = {
        "schema_version": 1,
        "protocol": {
            "dataset_sha256": sha256_file(args.dataset),
            "real_structured_names_only": True,
            "orcid_used_as_label_only": True,
            "mention_level_data_emitted": False,
            "candidate_universe_changed": False,
            "task": "incremental_open_set_rnd",
            "train": {
                "history_through": args.train_history_cutoff,
                "query_year": args.train_year,
            },
            "validation": {
                "history_through": args.evaluation_history_cutoff,
                "query_year": args.validation_year,
                "paper_hash_certification_modulus": args.validation_certification_modulus,
                "certification_label_status": args.certification_status,
            },
            "development_transfer": {
                "role": "development_transfer_benchmark",
                "final_claim_eligible": False,
                "query_from_year": args.test_from_year,
            },
        },
        "model": {
            "architecture": "grouped_lambdarank_then_binary_nil_gate",
            "ranker_feature_group": args.ranker_feature_group,
            "ranker": model_summary(ranker, ranker_feature_names),
            "nil_gate": model_summary(nil_gate, GATE_FEATURE_NAMES),
            "complexity": {
                "ranker_online_time": "O(C*T_rank*d_rank)",
                "nil_gate_online_time": "O(T_gate*d_gate)",
                "current_feature_extraction_time": "O(K^2 + K*profile_context)",
                "candidate_cap": 100,
                "retained_topk": 20,
                "full_catalog_scan": False,
            },
        },
        "training": training_summary,
        "validation": validation_summary,
        "certification": certification_summary,
        "development_transfer": {
            "ranking": ranking_metrics(
                transfer_groups,
                transfer_decisions,
                known_trials=transfer_known,
                new_trials=transfer_new,
            ),
            "istina_hypergraph_proxy": aggregate_method(transfer, proxy),
            "project2_base": aggregate_method(transfer, base),
            "project2_native_graph_threshold_0_5": aggregate_method(transfer, native),
            "project2_grouped_ranker_nil_gate": aggregate_method(
                transfer, selected_predictions
            ),
            "paired_known": {
                "vs_base": paired_binary(records, selected_predictions, base, known=True),
                "vs_native": paired_binary(records, selected_predictions, native, known=True),
                "vs_proxy": paired_binary(records, selected_predictions, proxy, known=True),
            },
            "paired_unseen_safe_rejection": {
                "vs_base": paired_binary(records, selected_predictions, base, known=False),
                "vs_native": paired_binary(records, selected_predictions, native, known=False),
                "vs_proxy": paired_binary(records, selected_predictions, proxy, known=False),
            },
        },
        "limitations": [
            "All 2022 and 2023+ labels are development-only after earlier experiments.",
            "The official S2AND/WhoIsWho baseline is not yet reproduced on this protocol.",
            "Independent verified ISTINA person-ID labels remain required.",
            "The model is an offline ablation and is not enabled in the runtime.",
        ],
    }
    report["runtime"] = {
        "wall_seconds": time.perf_counter() - wall_started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_working_set_bytes": peak_working_set_bytes(),
        "development_transfer_wall_seconds": transfer_wall,
        "development_transfer_queries_per_second": (
            transfer["test_mentions"] / transfer_wall if transfer_wall else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "report": str(args.output),
        "ranker_feature_group": args.ranker_feature_group,
        "validation_threshold": threshold,
        "statistical_risk_passed_on_opened_bucket": certificate[
            "statistical_risk_passed"
        ],
        "promotion_eligible": certificate["eligible_for_promotion"],
        "development_transfer_queries": transfer["test_mentions"],
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
