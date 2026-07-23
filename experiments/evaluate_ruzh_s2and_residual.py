"""Train and evaluate a temporally separated RuZh residual above S2AND.

The 2025+ official outcomes are not opened until the residual models, action
thresholds and artifact hash have been frozen from 2023 training and 2024
validation data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from disambiguation_engine.paper_graph_rescue import HistoricalCoauthorGraph
from disambiguation_engine.ruzh_name_evidence import RuZhNameEvidence
from disambiguation_engine.ruzh_residual_policy import (
    ResidualModels,
    ResidualPolicy,
    ResidualRow,
    apply_residual_policy,
    fit_residual_models,
    link_outcomes,
    score_residual_actions,
    select_residual_policy,
    threshold_family,
)
from experiments.audit_crossref_s2and_coverage import sha256_file
from experiments.compare_core_with_istina_proxy import (
    native_graph_records,
    project2_config,
)
from experiments.evaluate_listwise_graph_gate import (
    aggregate_method,
    base_predictions,
    native_predictions,
)
from experiments.evaluate_project2_s2and_public_replay import (
    _filter_mentions,
    _mapping_mention_fingerprint,
    _project2_mention,
    all_mentions,
)
from experiments.grouped_candidate_ranker import (
    GATE_FEATURE_NAMES,
    RANKER_FEATURE_GROUPS,
    build_candidate_groups,
    gate_feature_indices,
    load_frozen_model_bundle,
    out_of_fold_ranked_decisions,
    rank_groups,
)
from experiments.istina_runtime_replay import merge_evaluation_results
from experiments.run_s2and_official_public_baseline import (
    _filter_query_years,
    _identity_index,
)
from experiments.s2and_public_replay import (
    ReplayMention,
    load_replay_corpus,
)
from integrations.istina_pipeline import IstinaDisambiguationPipeline


SCHEMA_VERSION = "project2_ruzh_s2and_residual_public_v1"
ARTIFACT_SCHEMA_VERSION = "project2_ruzh_residual_bundle_v1"
RESIDUAL_META_FEATURE_NAMES = (
    "official_linked",
    "expert_agrees_official",
    "base_linked",
    "base_agrees_official",
    "base_agrees_expert",
    "native_linked",
    "native_agrees_official",
    "native_agrees_expert",
)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _git_output(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={PROJECT_ROOT.as_posix()}", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _load_cached_project2_replay(
    history_mentions: Sequence[ReplayMention],
    query_mentions: Sequence[ReplayMention],
    *,
    checkpoint_root: Path,
    phase: str,
    calibrated_candidate_threshold: float,
) -> dict[str, Any]:
    history = [
        _project2_mention(mention, index + 1)
        for index, mention in enumerate(history_mentions)
    ]
    test = [
        _project2_mention(mention, index + 1)
        for index, mention in enumerate(query_mentions)
    ]
    phase_name = f"{phase}.evaluate"
    phase_dir = checkpoint_root / phase_name
    batch_paths = sorted(phase_dir.glob("batch_*.json"))
    if not batch_paths:
        raise ValueError(f"cached Project Two phase is missing: {phase_name}")
    results = []
    cursor = 0
    for batch_path in batch_paths:
        payload = json.loads(batch_path.read_text(encoding="utf-8"))
        start = int(payload.get("start", -1))
        end = int(payload.get("end", -1))
        if (
            payload.get("phase") != phase_name
            or start != cursor
            or end <= start
            or end > len(test)
            or payload.get("mention_sha256")
            != _mapping_mention_fingerprint(test[start:end])
        ):
            raise ValueError(f"cached Project Two batch is misaligned: {batch_path}")
        results.append(payload["result"])
        cursor = end
    if cursor != len(test):
        raise ValueError(f"cached Project Two phase is incomplete: {phase_name}")
    project2 = merge_evaluation_results(results)
    if len(project2["records"]) != len(test):
        raise ValueError("cached Project Two record count is incorrect")

    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=project2_config(
            enable_calibrated_candidate_rescue=True,
            calibrated_candidate_threshold=calibrated_candidate_threshold,
        ),
        index_aliases=True,
    )
    graph = HistoricalCoauthorGraph.from_mentions(history)
    native = native_graph_records(
        history,
        project2["records"],
        test,
        list(range(len(test))),
        pipeline.history_state.repair_profiles,
        historical_graph=graph,
    )
    return {
        "history_mentions": len(history),
        "test_mentions": len(test),
        "project2": project2,
        "native": native,
        "profile_sizes": graph.profile_sizes,
        "history_mentions_raw": history,
        "test_mentions_raw": test,
    }


def _official_predictions(
    *,
    run_dir: Path,
    authors: Path,
    article_authors: Path,
    enrichment_dir: Path,
    cutoff_year: int,
    query_year_from: int,
    query_year_through: int,
) -> dict[str, str | None]:
    result = json.loads(
        (run_dir / "aggregate_result.json").read_text(encoding="utf-8")
    )
    manifest = result["manifest"]
    expected = {
        "cutoff_year": cutoff_year,
        "query_year_from": query_year_from,
        "query_year_through": query_year_through,
        "store_query_outcomes": True,
    }
    observed = {key: manifest.get(key) for key in expected}
    if observed != expected or not result.get("complete"):
        raise ValueError(f"official outcome run has the wrong protocol: {run_dir}")

    corpus = load_replay_corpus(
        authors,
        article_authors,
        enrichment_dir,
        cutoff_year=cutoff_year,
    )
    corpus = _filter_query_years(
        corpus,
        query_year_from=query_year_from,
        query_year_through=query_year_through,
    )
    identity_index, partition_digest = _identity_index(corpus)
    if partition_digest != manifest["identity_partition_sha256"]:
        raise ValueError("official identity partition does not reproduce")
    identity_by_index = {
        index: identity for identity, index in identity_index.items()
    }

    connection = sqlite3.connect(
        f"file:{(run_dir / 'checkpoint.sqlite3').as_posix()}?mode=ro",
        uri=True,
    )
    try:
        payloads = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT payload FROM block_results ORDER BY ordinal"
            )
        ]
    finally:
        connection.close()
    output: dict[str, str | None] = {}
    for payload in payloads:
        outcomes = payload.get("query_outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("official checkpoint does not store query outcomes")
        for outcome in outcomes:
            key = str(outcome["query_key"])
            predicted = [
                identity_by_index[int(index)]
                for index in outcome["predicted_identity_indices"]
            ]
            if len(predicted) == 1:
                value = predicted[0]
            elif not predicted:
                value = None
            else:
                value = f"conflict:{key}"
            if key in output:
                raise ValueError("duplicate official query key")
            output[key] = value
    if len(output) != int(manifest["selected_query_authorships"]):
        raise ValueError("official query outcomes are incomplete")
    return output


def _residual_rows(
    replay: Mapping[str, Any],
    decisions: Sequence[Any],
    official: Mapping[str, str | None],
    gate_indices: Sequence[int],
) -> list[ResidualRow]:
    records = list(replay["project2"]["records"])
    queries = list(replay["test_mentions_raw"])
    decision_by_position = {decision.position: decision for decision in decisions}
    base = base_predictions(replay)
    native = native_predictions(replay)
    rows = []
    for position, (record, query) in enumerate(zip(records, queries, strict=True)):
        key = _query_key_from_mapping(query)
        if key not in official:
            raise ValueError("Project Two query is absent from official outcomes")
        official_prediction = official[key]
        decision = decision_by_position.get(position)
        expert = decision.prediction if decision is not None else None
        base_prediction = base[position]
        native_prediction = native[position]
        features: tuple[float, ...] = ()
        if decision is not None:
            features = tuple(
                float(decision.features[index]) for index in gate_indices
            ) + (
                float(official_prediction is not None),
                float(expert == official_prediction),
                float(base_prediction is not None),
                float(base_prediction == official_prediction),
                float(base_prediction == expert),
                float(native_prediction is not None),
                float(native_prediction == official_prediction),
                float(native_prediction == expert),
            )
        evidence = RuZhNameEvidence.from_mapping(query)
        rows.append(ResidualRow(
            query_key=key,
            target=evidence.target,
            known=bool(record.get("gold_seen_in_history")),
            truth=str(record.get("gold_author_id") or ""),
            official=official_prediction,
            expert=expert,
            features=features,
        ))
    return rows


def _query_key_from_mapping(query: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        (
            f"{str(query.get('article_id') or '').casefold()}"
            f"\0{int(query.get('position') or 0)}"
        ).encode("utf-8")
    ).hexdigest()


def _model_string(model: Any) -> str:
    booster = getattr(model, "booster_", model)
    return str(booster.model_to_string())


def _threshold_value(value: float) -> float | None:
    return None if math.isinf(value) else float(value)


def _freeze_residual_bundle(
    *,
    models: ResidualModels,
    policy: ResidualPolicy,
    feature_names: Sequence[str],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    encoded = json.dumps(
        protocol,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "contains_identity_values": False,
        "feature_names": list(feature_names),
        "replacement_threshold": _threshold_value(
            policy.replacement_threshold
        ),
        "veto_threshold": _threshold_value(policy.veto_threshold),
        "replacement_model": _model_string(models.replacement),
        "veto_model": _model_string(models.veto),
        "protocol_sha256": hashlib.sha256(encoded).hexdigest(),
        "protocol": dict(protocol),
    }


def _load_residual_bundle(
    payload: Mapping[str, Any],
) -> tuple[ResidualModels, ResidualPolicy]:
    if (
        payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION
        or payload.get("contains_identity_values") is not False
    ):
        raise ValueError("invalid residual bundle")
    import lightgbm

    def threshold(name: str) -> float:
        value = payload.get(name)
        return math.inf if value is None else float(value)

    return (
        ResidualModels(
            replacement=lightgbm.Booster(
                model_str=str(payload["replacement_model"])
            ),
            veto=lightgbm.Booster(model_str=str(payload["veto_model"])),
        ),
        ResidualPolicy(
            replacement_threshold=threshold("replacement_threshold"),
            veto_threshold=threshold("veto_threshold"),
        ),
    )


def _outcome_dict(value: Any) -> dict[str, int | float]:
    return {
        "known": value.known,
        "new": value.new,
        "correct_known": value.correct_known,
        "wrong_known": value.wrong_known,
        "false_links_new": value.false_links_new,
        "known_recall": value.known_recall,
        "wrong_known_rate": value.wrong_known_rate,
        "new_false_link_rate": value.new_false_link_rate,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    if _git_output(["status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("formal residual run requires a clean tracked worktree")
    revision = _git_output(["rev-parse", "HEAD"])
    source = load_replay_corpus(
        args.authors,
        args.article_authors,
        args.enrichment_dir,
        cutoff_year=args.comparison_history_through,
    )
    mentions = all_mentions(source)
    project2_bundle = load_frozen_model_bundle(
        json.loads(args.project2_model.read_text(encoding="utf-8"))
    )
    feature_indices = project2_bundle.ranker_feature_indices
    gate_indices = gate_feature_indices(feature_indices)
    feature_names = [
        GATE_FEATURE_NAMES[index] for index in gate_indices
    ] + list(RESIDUAL_META_FEATURE_NAMES)
    if tuple(feature_indices) != tuple(
        RANKER_FEATURE_GROUPS["listwise_ruzh_profile_hard_negative"]
    ):
        raise ValueError("Project Two bundle is not the registered RuZh model")

    train_history = _filter_mentions(
        mentions, through_year=args.train_history_through
    )
    train_query = _filter_mentions(mentions, exact_year=args.train_query_year)
    train_replay = _load_cached_project2_replay(
        train_history,
        train_query,
        checkpoint_root=args.project2_checkpoint,
        phase="train",
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
    )
    train_groups = build_candidate_groups(
        train_replay,
        include_multilingual=True,
        include_ruzh_lexicon=True,
        include_ruzh_profile=True,
    )
    train_decisions = out_of_fold_ranked_decisions(
        train_groups,
        feature_indices,
        folds=args.oof_folds,
    )
    train_official = _official_predictions(
        run_dir=args.official_train,
        authors=args.authors,
        article_authors=args.article_authors,
        enrichment_dir=args.enrichment_dir,
        cutoff_year=args.train_history_through,
        query_year_from=args.train_query_year,
        query_year_through=args.train_query_year,
    )
    train_rows = _residual_rows(
        train_replay, train_decisions, train_official, gate_indices
    )
    models = fit_residual_models(train_rows)
    train_replacement, train_veto = score_residual_actions(models, train_rows)
    replacement_thresholds = threshold_family(
        tuple(train_replacement.values()),
        size=args.threshold_family_size,
    )
    veto_thresholds = threshold_family(
        tuple(train_veto.values()),
        size=args.threshold_family_size,
    )
    print(
        "residual_train_complete "
        f"queries={len(train_rows)} target={sum(row.target for row in train_rows)} "
        f"replacement_examples={len(train_replacement)} veto_examples={len(train_veto)}"
    )

    validation_history = _filter_mentions(
        mentions, through_year=args.validation_history_through
    )
    validation_official = _official_predictions(
        run_dir=args.official_validation,
        authors=args.authors,
        article_authors=args.article_authors,
        enrichment_dir=args.enrichment_dir,
        cutoff_year=args.validation_history_through,
        query_year_from=args.validation_query_year,
        query_year_through=args.validation_query_year,
    )
    validation_rows = []
    for phase, invert_bucket in (
        ("validation_selection", True),
        ("validation_certification", False),
    ):
        query = _filter_mentions(
            mentions,
            exact_year=args.validation_query_year,
            paper_bucket_modulus=args.validation_modulus,
            paper_bucket=0,
            invert_bucket=invert_bucket,
        )
        replay = _load_cached_project2_replay(
            validation_history,
            query,
            checkpoint_root=args.project2_checkpoint,
            phase=phase,
            calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        )
        groups = build_candidate_groups(
            replay,
            include_multilingual=True,
            include_ruzh_lexicon=True,
            include_ruzh_profile=True,
        )
        decisions = rank_groups(
            project2_bundle.ranker, groups, feature_indices
        )
        validation_rows.extend(
            _residual_rows(
                replay, decisions, validation_official, gate_indices
            )
        )
    if len(validation_rows) != len(validation_official):
        raise ValueError("validation query partitions are incomplete")
    validation_replacement, validation_veto = score_residual_actions(
        models, validation_rows
    )
    policy, validation_deltas = select_residual_policy(
        validation_rows,
        validation_replacement,
        validation_veto,
        replacement_thresholds,
        veto_thresholds,
    )
    validation_predictions = apply_residual_policy(
        validation_rows,
        validation_replacement,
        validation_veto,
        policy,
    )
    print(
        "residual_validation_complete "
        f"queries={len(validation_rows)} "
        f"correct_delta={validation_deltas['correct_known']} "
        f"wrong_delta={validation_deltas['wrong_known']} "
        f"new_false_delta={validation_deltas['false_links_new']}"
    )

    protocol = {
        "project_revision": revision,
        "project2_model_sha256": sha256_file(args.project2_model),
        "project2_checkpoint_manifest_sha256": sha256_file(
            args.project2_checkpoint / "manifest.json"
        ),
        "official_train_checkpoint_sha256": sha256_file(
            args.official_train / "checkpoint.sqlite3"
        ),
        "official_validation_checkpoint_sha256": sha256_file(
            args.official_validation / "checkpoint.sqlite3"
        ),
        "train": {
            "history_through": args.train_history_through,
            "query_year": args.train_query_year,
        },
        "validation": {
            "history_through": args.validation_history_through,
            "query_year": args.validation_query_year,
        },
        "comparison": {
            "history_through": args.comparison_history_through,
            "query_from": args.comparison_query_from,
        },
        "threshold_family_size": args.threshold_family_size,
        "action_order": ["replacement", "veto", "official_fallback"],
        "non_target_action_enabled": False,
        "comparison_outcomes_opened_after_artifact_freeze": True,
    }
    bundle = _freeze_residual_bundle(
        models=models,
        policy=policy,
        feature_names=feature_names,
        protocol=protocol,
    )
    _atomic_json(args.model_artifact, bundle)
    artifact_sha256 = sha256_file(args.model_artifact)
    models, policy = _load_residual_bundle(
        json.loads(args.model_artifact.read_text(encoding="utf-8"))
    )
    # The comparison outcome checkpoint is deliberately not touched above.
    artifact_frozen_before_comparison = True

    comparison_history = _filter_mentions(
        mentions, through_year=args.comparison_history_through
    )
    comparison_query = _filter_mentions(
        mentions, from_year=args.comparison_query_from
    )
    comparison_replay = _load_cached_project2_replay(
        comparison_history,
        comparison_query,
        checkpoint_root=args.project2_checkpoint,
        phase="comparison",
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
    )
    comparison_groups = build_candidate_groups(
        comparison_replay,
        include_multilingual=True,
        include_ruzh_lexicon=True,
        include_ruzh_profile=True,
    )
    comparison_decisions = rank_groups(
        project2_bundle.ranker,
        comparison_groups,
        feature_indices,
    )
    comparison_official = _official_predictions(
        run_dir=args.official_comparison,
        authors=args.authors,
        article_authors=args.article_authors,
        enrichment_dir=args.enrichment_dir,
        cutoff_year=args.comparison_history_through,
        query_year_from=args.comparison_query_from,
        query_year_through=args.comparison_query_through,
    )
    comparison_rows = _residual_rows(
        comparison_replay,
        comparison_decisions,
        comparison_official,
        gate_indices,
    )
    comparison_replacement, comparison_veto = score_residual_actions(
        models, comparison_rows
    )
    candidate_predictions = apply_residual_policy(
        comparison_rows,
        comparison_replacement,
        comparison_veto,
        policy,
    )
    official_predictions = [row.official for row in comparison_rows]
    target_official = link_outcomes(
        comparison_rows, official_predictions, target=True
    )
    target_candidate = link_outcomes(
        comparison_rows, candidate_predictions, target=True
    )
    non_target_disagreements = sum(
        not row.target and candidate != row.official
        for row, candidate in zip(
            comparison_rows, candidate_predictions, strict=True
        )
    )
    from disambiguation_engine.ruzh_conditional_expert import (
        joint_promotion_gate,
    )

    gate = joint_promotion_gate(
        target_official,
        target_candidate,
        non_target_trials=sum(not row.target for row in comparison_rows),
        non_target_disagreements=non_target_disagreements,
    )
    official_aggregate = aggregate_method(
        comparison_replay, official_predictions
    )
    candidate_aggregate = aggregate_method(
        comparison_replay, candidate_predictions
    )
    action_counts = Counter()
    for row, candidate in zip(
        comparison_rows, candidate_predictions, strict=True
    ):
        if candidate == row.official:
            action_counts["official_fallback"] += 1
        elif candidate is None:
            action_counts["veto"] += 1
        else:
            action_counts["replacement"] += 1

    report = {
        "schema_version": SCHEMA_VERSION,
        "development_only": True,
        "contains_record_values": False,
        "artifact_frozen_before_comparison": artifact_frozen_before_comparison,
        "model_artifact_sha256": artifact_sha256,
        "protocol": protocol,
        "training": {
            "queries": len(train_rows),
            "target_queries": sum(row.target for row in train_rows),
            "replacement_examples": len(train_replacement),
            "veto_examples": len(train_veto),
        },
        "validation": {
            "queries": len(validation_rows),
            "target_queries": sum(row.target for row in validation_rows),
            "deltas": dict(validation_deltas),
            "official_target": _outcome_dict(
                link_outcomes(
                    validation_rows,
                    [row.official for row in validation_rows],
                    target=True,
                )
            ),
            "candidate_target": _outcome_dict(
                link_outcomes(
                    validation_rows,
                    validation_predictions,
                    target=True,
                )
            ),
        },
        "comparison": {
            "queries": len(comparison_rows),
            "target_queries": sum(row.target for row in comparison_rows),
            "action_counts": dict(action_counts),
            "official_target": _outcome_dict(target_official),
            "candidate_target": _outcome_dict(target_candidate),
            "promotion_gate": {
                "passed": gate.passed,
                "reasons": list(gate.reasons),
                "deltas": dict(gate.deltas),
            },
            "official_overall": official_aggregate,
            "candidate_overall": candidate_aggregate,
        },
        "complexity": {
            "wall_seconds": time.perf_counter() - started,
        },
    }
    _atomic_json(args.output, report)
    print(
        "residual_comparison_complete "
        f"queries={len(comparison_rows)} target={sum(row.target for row in comparison_rows)} "
        f"passed={gate.passed} correct_delta={gate.deltas['correct_known']} "
        f"wrong_delta={gate.deltas['wrong_known']} "
        f"new_false_delta={gate.deltas['false_links_new']}"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--project2-checkpoint", type=Path, required=True)
    parser.add_argument("--project2-model", type=Path, required=True)
    parser.add_argument("--official-train", type=Path, required=True)
    parser.add_argument("--official-validation", type=Path, required=True)
    parser.add_argument("--official-comparison", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-history-through", type=int, default=2022)
    parser.add_argument("--train-query-year", type=int, default=2023)
    parser.add_argument("--validation-history-through", type=int, default=2023)
    parser.add_argument("--validation-query-year", type=int, default=2024)
    parser.add_argument("--validation-modulus", type=int, default=5)
    parser.add_argument("--comparison-history-through", type=int, default=2024)
    parser.add_argument("--comparison-query-from", type=int, default=2025)
    parser.add_argument("--comparison-query-through", type=int, default=9999)
    parser.add_argument("--oof-folds", type=int, default=5)
    parser.add_argument("--threshold-family-size", type=int, default=12)
    parser.add_argument(
        "--calibrated-candidate-threshold",
        type=float,
        default=0.995,
    )
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
