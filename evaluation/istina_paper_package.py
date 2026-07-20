"""Build a fail-closed, article-ready package from current ISTINA evidence.

The composer verifies cross-artifact hashes, dataset identity, split semantics,
de-duplication, metric/gate consistency, and the explicit retirement of the
leakage-affected historical ISTINA result before it emits paper tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nearest_rank_percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _same(observed: Any, expected: Any) -> bool:
    if isinstance(observed, bool) or isinstance(expected, bool):
        return observed is expected
    if isinstance(observed, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(observed), float(expected), rel_tol=0.0, abs_tol=1e-12)
    return observed == expected


def _check(name: str, observed: Any, expected: Any, passed: bool | None = None) -> Dict[str, Any]:
    return {
        "name": name,
        "observed": observed,
        "expected": expected,
        "passed": _same(observed, expected) if passed is None else bool(passed),
    }


def _gate_observed(gate: Mapping[str, Any], name: str) -> Any:
    for check in gate.get("checks") or []:
        if isinstance(check, Mapping) and check.get("name") == name:
            return check.get("observed")
    return None


def _paired_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {
        "both_correct": 0,
        "runtime_only_correct": 0,
        "legacy_only_correct": 0,
        "both_incorrect": 0,
    }
    for record in records:
        runtime_correct = record.get("runtime_correct") is True
        legacy_correct = record.get("legacy_correct") is True
        if runtime_correct and legacy_correct:
            counts["both_correct"] += 1
        elif runtime_correct:
            counts["runtime_only_correct"] += 1
        elif legacy_correct:
            counts["legacy_only_correct"] += 1
        else:
            counts["both_incorrect"] += 1
    return counts


def _mcnemar_exact_two_sided(runtime_only: int, legacy_only: int) -> float:
    discordant = runtime_only + legacy_only
    if discordant == 0:
        return 1.0
    smaller = min(runtime_only, legacy_only)
    lower_tail = sum(
        math.comb(discordant, index)
        for index in range(smaller + 1)
    ) / (2 ** discordant)
    return min(1.0, 2.0 * lower_tail)


def _live_shadow_record_is_redacted(record: Mapping[str, Any]) -> bool:
    allowed_fields = {
        "article_id_hash",
        "position",
        "gold_author_id_hash",
        "runtime_correct",
        "legacy_correct",
        "decision",
        "stage",
        "legacy_result_present",
        "legacy_candidate_count",
        "service_error",
        "deterministic_hash",
    }
    return bool(
        set(record) == allowed_fields
        and re.fullmatch(r"[0-9a-f]{16}", str(record.get("article_id_hash") or ""))
        and re.fullmatch(
            r"[0-9a-f]{16}",
            str(record.get("gold_author_id_hash") or ""),
        )
        and re.fullmatch(
            r"[0-9a-f]{16}",
            str(record.get("deterministic_hash") or ""),
        )
        and str(record.get("position") or "").isdigit()
        and record.get("decision") in {"merge", "new", "unknown"}
        and isinstance(record.get("stage"), str)
        and re.fullmatch(r"[a-z0-9_.:-]{1,64}", record["stage"])
        and all(
            isinstance(record.get(field), bool)
            for field in (
                "runtime_correct",
                "legacy_correct",
                "legacy_result_present",
                "service_error",
            )
        )
        and isinstance(record.get("legacy_candidate_count"), int)
        and not isinstance(record.get("legacy_candidate_count"), bool)
        and int(record["legacy_candidate_count"]) >= 0
    )


def _quality_row(
    dataset: str,
    protocol_role: str,
    result: Mapping[str, Any],
    paper_overlap: Any,
    source: str,
) -> Dict[str, Any]:
    stats = dict(result.get("stats") or result)
    metrics = dict(result.get("metrics") or result)
    total = int(stats.get("total", stats.get("test_mentions", 0)) or 0)
    existing = int(stats.get("existing_gold", 0) or 0)
    new = int(stats.get("new_gold", 0) or 0)
    wrong = int(stats.get("wrong_merge", 0) or 0)
    return {
        "dataset": dataset,
        "protocol_role": protocol_role,
        "test_mentions": total,
        "existing_mentions": existing,
        "new_mentions": new,
        "paper_overlap": paper_overlap,
        "merge_precision": metrics.get("precision", metrics.get("merge_precision")),
        "existing_recall": metrics.get("existing_recall"),
        "automatic_accuracy": metrics.get("auto_accuracy", metrics.get("automatic_accuracy")),
        "unknown_rate": metrics.get("unknown_rate"),
        "wrong_merge_rate": metrics.get(
            "wrong_merge_rate",
            wrong / total if total else None,
        ),
        "p95_latency_ms": metrics.get("latency_ms_p95", metrics.get("p95_latency_ms")),
        "source": source,
    }


def compose_paper_package(
    *,
    temporal: Mapping[str, Any],
    holdout: Mapping[str, Any],
    operational: Mapping[str, Any],
    gold: Mapping[str, Any],
    live: Mapping[str, Any],
    live_diagnostic: Mapping[str, Any],
    online_canary: Mapping[str, Any],
    performance_reproducibility: Mapping[str, Any],
    bundle: Mapping[str, Any],
    gate: Mapping[str, Any],
    openalex_default: Mapping[str, Any],
    openalex_rescue: Mapping[str, Any],
    openalex_large_default: Mapping[str, Any],
    openalex_large_rescue: Mapping[str, Any],
    aminer_full_current: Mapping[str, Any],
    aminer_full_rescue_current: Mapping[str, Any],
    aminer_default_current: Mapping[str, Any],
    aminer_rescue_current: Mapping[str, Any],
    public_validation: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, str]],
    generated_at: str | None = None,
) -> Dict[str, Any]:
    temporal_protocol = dict(temporal.get("protocol") or {})
    holdout_protocol = dict(holdout.get("protocol") or {})
    operational_protocol = dict(operational.get("protocol") or {})
    live_protocol = dict(live.get("protocol") or {})
    live_diagnostic_protocol = dict(live_diagnostic.get("protocol") or {})
    online_canary_protocol = dict(online_canary.get("protocol") or {})
    online_canary_stats = dict(online_canary.get("stats") or {})
    online_canary_metrics = dict(online_canary.get("metrics") or {})
    online_canary_safety = dict(online_canary.get("safety") or {})
    performance_protocol = dict(
        performance_reproducibility.get("protocol") or {}
    )
    performance_summary = dict(
        performance_reproducibility.get("summary") or {}
    )
    performance_metrics = dict(
        performance_reproducibility.get("metrics") or {}
    )
    performance_trials = [
        dict(item)
        for item in (performance_reproducibility.get("trials") or [])
        if isinstance(item, Mapping)
    ]
    temporal_stats = dict(temporal.get("stats") or {})
    holdout_stats = dict(holdout.get("stats") or {})
    holdout_legacy = dict(holdout.get("legacy_shadow") or {})
    live_diagnostic_stats = dict(live_diagnostic.get("stats") or {})
    live_diagnostic_safety = dict(live_diagnostic.get("safety") or {})
    live_diagnostic_records = [
        record
        for record in (live_diagnostic.get("records") or [])
        if isinstance(record, Mapping)
    ]
    live_diagnostic_paired = _paired_counts(live_diagnostic_records)
    temporal_metrics = dict(temporal.get("metrics") or {})
    holdout_metrics = dict(holdout.get("metrics") or {})
    gold_temporal = dict(gold.get("production_temporal_split") or {})
    gold_holdout = dict(gold.get("diagnostic_per_author_holdout") or {})
    gold_dataset = dict(gold.get("dataset") or {})
    gold_inputs = dict(gold.get("inputs") or {})
    openalex_default_protocol = dict(openalex_default.get("protocol") or {})
    openalex_rescue_protocol = dict(openalex_rescue.get("protocol") or {})
    openalex_large_default_protocol = dict(
        openalex_large_default.get("protocol") or {}
    )
    openalex_large_rescue_protocol = dict(
        openalex_large_rescue.get("protocol") or {}
    )
    aminer_full_protocol = dict(aminer_full_current.get("protocol") or {})
    aminer_full_rescue_protocol = dict(
        aminer_full_rescue_current.get("protocol") or {}
    )
    aminer_default_protocol = dict(aminer_default_current.get("protocol") or {})
    aminer_rescue_protocol = dict(aminer_rescue_current.get("protocol") or {})
    public_results = dict(public_validation.get("results") or {})

    gold_dataset_hashes = {
        str(item.get("sha256") or "")
        for item in gold_inputs.get("datasets") or []
        if isinstance(item, Mapping) and item.get("sha256")
    }
    dataset_hashes = gold_dataset_hashes | {
        str(temporal_protocol.get("dataset_sha256") or ""),
        str(holdout_protocol.get("dataset_sha256") or ""),
        str(operational_protocol.get("dataset_sha256") or ""),
        str(live_protocol.get("dataset_sha256") or ""),
        str(live_diagnostic_protocol.get("dataset_sha256") or ""),
        str(online_canary_protocol.get("dataset_sha256") or ""),
        str(performance_protocol.get("dataset_sha256") or ""),
    }
    dataset_hashes.discard("")
    service_hashes = {
        str(temporal_protocol.get("service_result_sha256") or ""),
        str(holdout_protocol.get("service_result_sha256") or ""),
        str(operational_protocol.get("service_result_sha256") or ""),
        str((gold_inputs.get("service_result") or {}).get("sha256") or ""),
    }
    service_hashes.discard("")
    duplicate_counts = {
        int(temporal_protocol.get("exact_duplicate_author_rows_removed") or 0),
        int(holdout_protocol.get("exact_duplicate_author_rows_removed") or 0),
        int(operational_protocol.get("exact_duplicate_author_rows_removed") or 0),
        int(live_protocol.get("exact_duplicate_author_rows_removed") or 0),
        int(
            live_diagnostic_protocol.get("exact_duplicate_author_rows_removed")
            or 0
        ),
        int(
            ((gold_dataset.get("automatic_cleaning") or {}).get(
                "exact_duplicate_author_rows_removed"
            ))
            or 0
        ),
    }
    comparator_protocols = {
        "temporal": [
            temporal_protocol.get("framework_legacy_fallback_enabled"),
            temporal_protocol.get("legacy_service_observation_only"),
            int((temporal.get("stage_counts") or {}).get(
                "legacy_service_validated_fallback"
            ) or 0),
        ],
        "holdout": [
            holdout_protocol.get("framework_legacy_fallback_enabled"),
            holdout_protocol.get("legacy_service_observation_only"),
            int((holdout.get("stage_counts") or {}).get(
                "legacy_service_validated_fallback"
            ) or 0),
        ],
        "operational": [
            operational_protocol.get("framework_legacy_fallback_enabled"),
            operational_protocol.get("legacy_service_observation_only"),
            int((operational.get("stage_counts") or {}).get(
                "legacy_service_validated_fallback"
            ) or 0),
        ],
        "live": [
            live_protocol.get("framework_legacy_fallback_enabled"),
            live_protocol.get("legacy_service_observation_only"),
            sum(
                isinstance(record, Mapping)
                and record.get("stage") == "legacy_service_validated_fallback"
                for record in (live.get("records") or [])
            ),
        ],
        "live_diagnostic": [
            live_diagnostic_protocol.get("framework_legacy_fallback_enabled"),
            live_diagnostic_protocol.get("legacy_service_observation_only"),
            sum(
                record.get("stage") == "legacy_service_validated_fallback"
                for record in live_diagnostic_records
            ),
        ],
    }
    bundle_sources = dict(bundle.get("sources") or {})
    checks = [
        _check(
            "bundle_operational_sha256",
            (bundle_sources.get("operational_validation") or {}).get("sha256"),
            (sources.get("operational") or {}).get("sha256"),
        ),
        _check(
            "bundle_gold_sha256",
            (bundle_sources.get("gold_readiness") or {}).get("sha256"),
            (sources.get("gold") or {}).get("sha256"),
        ),
        _check(
            "bundle_live_sha256",
            (bundle_sources.get("live_shadow") or {}).get("sha256"),
            (sources.get("live") or {}).get("sha256"),
        ),
        _check("single_dataset_sha256", sorted(dataset_hashes), "one non-empty hash", len(dataset_hashes) == 1),
        _check("single_legacy_service_sha256", sorted(service_hashes), "one non-empty hash", len(service_hashes) == 1),
        _check("temporal_split", temporal_protocol.get("split_strategy"), "temporal"),
        _check("diagnostic_split", holdout_protocol.get("split_strategy"), "per-author-holdout"),
        _check(
            "exact_duplicate_cleaning",
            sorted(duplicate_counts),
            [52],
            duplicate_counts == {52}
            and all(
                protocol.get("exact_duplicate_cleaning_applied") is True
                for protocol in (
                    temporal_protocol,
                    holdout_protocol,
                    operational_protocol,
                    live_protocol,
                    live_diagnostic_protocol,
                )
            ),
        ),
        _check(
            "legacy_comparator_independence",
            {
                "protocols": comparator_protocols,
                "gate": _gate_observed(
                    gate,
                    "legacy_comparator_independence_verified",
                ),
            },
            "all framework paths [fallback=False, observation_only=True, fallback_stages=0] and gate=true",
            all(
                values == [False, True, 0]
                for values in comparator_protocols.values()
            )
            and _gate_observed(
                gate,
                "legacy_comparator_independence_verified",
            ) is True,
        ),
        _check(
            "live_diagnostic_dataset_sha256",
            live_diagnostic_protocol.get("dataset_sha256"),
            next(iter(dataset_hashes), None) if len(dataset_hashes) == 1 else None,
        ),
        _check(
            "live_diagnostic_split",
            live_diagnostic_protocol.get("split_strategy"),
            "per-author-holdout",
        ),
        _check(
            "live_diagnostic_code_revision",
            live_diagnostic_protocol.get("code_revision"),
            "full 40-hex frozen Git revision",
            re.fullmatch(
                r"[0-9a-f]{40}",
                str(live_diagnostic_protocol.get("code_revision") or ""),
            )
            is not None,
        ),
        _check(
            "live_diagnostic_sample_matches_holdout",
            {
                "attempted_mentions": live_diagnostic_stats.get(
                    "attempted_mentions"
                ),
                "records": len(live_diagnostic_records),
                "paper_requests": live_diagnostic_protocol.get("paper_requests"),
            },
            {
                "attempted_mentions": holdout_legacy.get("n"),
                "records": holdout_legacy.get("n"),
                "paper_requests": "positive",
            },
            live_diagnostic_stats.get("attempted_mentions")
            == holdout_legacy.get("n")
            == len(live_diagnostic_records)
            and int(live_diagnostic_protocol.get("paper_requests") or 0) > 0,
        ),
        _check(
            "live_diagnostic_paired_counts_internally_consistent",
            {
                "paired_table": live_diagnostic_paired,
                "runtime_correct": live_diagnostic_stats.get("runtime_correct"),
                "legacy_correct": live_diagnostic_stats.get("legacy_correct"),
                "records": len(live_diagnostic_records),
            },
            "paired cells sum to records and reproduce both correctness totals",
            sum(live_diagnostic_paired.values()) == len(live_diagnostic_records)
            and int(live_diagnostic_stats.get("runtime_correct") or 0)
            == int(live_diagnostic_paired.get("both_correct") or 0)
            + int(live_diagnostic_paired.get("runtime_only_correct") or 0)
            and int(live_diagnostic_stats.get("legacy_correct") or 0)
            == int(live_diagnostic_paired.get("both_correct") or 0)
            + int(live_diagnostic_paired.get("legacy_only_correct") or 0),
        ),
        _check(
            "live_diagnostic_framework_matches_frozen_framework",
            live_diagnostic_stats.get("runtime_correct"),
            holdout_legacy.get("runtime_correct"),
        ),
        _check(
            "live_diagnostic_no_write_safety",
            {
                "smoke_verified": live_diagnostic_safety.get(
                    "online_shadow_smoke_verified"
                ),
                "write_calls": live_diagnostic_protocol.get("write_calls"),
                "authorized_commands": live_diagnostic_stats.get(
                    "authorized_commands"
                ),
                "no_write_authorized": live_diagnostic_safety.get(
                    "no_write_authorized"
                ),
                "audit_verified": (
                    live_diagnostic_safety.get("durable_audit_chain") or {}
                ).get("verified"),
            },
            {
                "smoke_verified": True,
                "write_calls": 0,
                "authorized_commands": 0,
                "no_write_authorized": True,
                "audit_verified": True,
            },
        ),
        _check(
            "live_diagnostic_records_redacted",
            sum(
                _live_shadow_record_is_redacted(record)
                for record in live_diagnostic_records
            ),
            len(live_diagnostic_records),
        ),
        _check(
            "live_diagnostic_service_observations_complete",
            {
                "service_errors": live_diagnostic_stats.get("service_errors"),
                "service_successful_mentions": live_diagnostic_stats.get(
                    "service_successful_mentions"
                ),
                "legacy_result_present": live_diagnostic_stats.get(
                    "legacy_result_present"
                ),
            },
            {
                "service_errors": 0,
                "service_successful_mentions": live_diagnostic_stats.get(
                    "attempted_mentions"
                ),
                "legacy_result_present": "between zero and attempted; no-match is valid",
            },
            live_diagnostic_stats.get("service_errors") == 0
            and live_diagnostic_stats.get("service_successful_mentions")
            == live_diagnostic_stats.get("attempted_mentions")
            and 0
            <= int(live_diagnostic_stats.get("legacy_result_present") or 0)
            <= int(live_diagnostic_stats.get("attempted_mentions") or 0),
        ),
        _check(
            "live_diagnostic_remains_non_release",
            {
                "verified": (
                    (live_diagnostic.get("operational_evidence") or {}).get(
                        "online_shadow_verified"
                    )
                    or {}
                ).get("verified"),
                "mentions": live_diagnostic_stats.get("attempted_mentions"),
                "minimum": (
                    (live_diagnostic.get("operational_evidence") or {}).get(
                        "online_shadow_verified"
                    )
                    or {}
                ).get("minimum_release_shadow_mentions"),
            },
            "verified=false and mentions below the release minimum",
            (
                (live_diagnostic.get("operational_evidence") or {}).get(
                    "online_shadow_verified"
                )
                or {}
            ).get("verified")
            is False
            and int(live_diagnostic_stats.get("attempted_mentions") or 0)
            < int(
                (
                    (live_diagnostic.get("operational_evidence") or {}).get(
                        "online_shadow_verified"
                    )
                    or {}
                ).get("minimum_release_shadow_mentions")
                or 0
            ),
        ),
        _check(
            "online_canary_dataset_sha256",
            online_canary_protocol.get("dataset_sha256"),
            next(iter(dataset_hashes), None) if len(dataset_hashes) == 1 else None,
        ),
        _check(
            "online_canary_code_revision",
            online_canary_protocol.get("code_revision"),
            "full 40-hex frozen Git revision",
            re.fullmatch(
                r"[0-9a-f]{40}",
                str(online_canary_protocol.get("code_revision") or ""),
            )
            is not None,
        ),
        _check(
            "online_canary_protocol",
            {
                "schema_version": online_canary.get("schema_version"),
                "source_system": online_canary_protocol.get("source_system"),
                "mode": online_canary_protocol.get("mode"),
                "approval_scope": online_canary_protocol.get("approval_scope"),
                "approved_change_reference": bool(
                    str(
                        online_canary_protocol.get("approved_change_reference")
                        or ""
                    ).strip()
                ),
                "duplicate_rows_removed": online_canary_protocol.get(
                    "exact_duplicate_author_rows_removed"
                ),
            },
            {
                "schema_version": 1,
                "source_system": "istina",
                "mode": "read_only_candidate_lookup",
                "approval_scope": "user_authorized_canary",
                "approved_change_reference": True,
                "duplicate_rows_removed": 52,
            },
        ),
        _check(
            "online_canary_execution",
            {
                "protocol_requests": online_canary_protocol.get("requests"),
                "stats_requests": online_canary_stats.get("requests"),
                "completed": online_canary_stats.get("completed"),
                "errors": online_canary_stats.get("errors"),
                "error_rate": online_canary_metrics.get("error_rate"),
                "p95_ms": online_canary_metrics.get("latency_ms_p95"),
            },
            "positive equal request/completion counts, zero errors, finite p95 within canary criterion",
            not isinstance(online_canary_stats.get("requests"), bool)
            and isinstance(online_canary_stats.get("requests"), int)
            and int(online_canary_stats["requests"]) > 0
            and online_canary_protocol.get("requests")
            == online_canary_stats.get("requests")
            == online_canary_stats.get("completed")
            and online_canary_stats.get("errors") == 0
            and online_canary_metrics.get("error_rate") == 0.0
            and isinstance(
                online_canary_metrics.get("latency_ms_p95"),
                (int, float),
            )
            and not isinstance(
                online_canary_metrics.get("latency_ms_p95"),
                bool,
            )
            and math.isfinite(
                float(online_canary_metrics.get("latency_ms_p95"))
            )
            and 0.0
            <= float(online_canary_metrics.get("latency_ms_p95"))
            <= float(
                (online_canary_safety.get("criteria") or {}).get(
                    "max_p95_latency_ms"
                )
                or 0.0
            ),
        ),
        _check(
            "online_canary_remains_non_release",
            {
                "verified": online_canary_safety.get("verified"),
                "threshold_passed": online_canary_safety.get(
                    "threshold_passed"
                ),
                "institutional_approval": online_canary_safety.get(
                    "institutional_approval"
                ),
                "classification": online_canary_safety.get(
                    "evidence_classification"
                ),
                "write_client_present": online_canary_safety.get(
                    "write_client_present"
                ),
                "write_calls": online_canary_stats.get("write_calls"),
                "acknowledged": online_canary_safety.get(
                    "explicit_operator_acknowledgement"
                ),
                "requests": online_canary_stats.get("requests"),
                "minimum": (
                    online_canary_safety.get("criteria") or {}
                ).get("min_requests"),
            },
            "bounded user-authorized canary, below release volume, with no write client or calls",
            online_canary_safety.get("verified") is False
            and online_canary_safety.get("threshold_passed") is False
            and online_canary_safety.get("institutional_approval") is False
            and online_canary_safety.get("evidence_classification")
            == "bounded_non_release_canary"
            and online_canary_safety.get("write_client_present") is False
            and online_canary_safety.get("write_calls") == 0
            and online_canary_stats.get("write_calls") == 0
            and online_canary_safety.get("explicit_operator_acknowledgement")
            is True
            and int(online_canary_stats.get("requests") or 0)
            < int(
                (online_canary_safety.get("criteria") or {}).get(
                    "min_requests"
                )
                or 0
            ),
        ),
        _check(
            "offline_performance_reproducibility_dataset",
            performance_protocol.get("dataset_sha256"),
            next(iter(dataset_hashes), None) if len(dataset_hashes) == 1 else None,
        ),
        _check(
            "offline_performance_reproducibility_code_binding",
            {
                "aggregate": performance_protocol.get("code_revision"),
                "operational": operational_protocol.get("code_revision"),
            },
            "identical full 40-hex frozen revisions",
            re.fullmatch(
                r"[0-9a-f]{40}",
                str(performance_protocol.get("code_revision") or ""),
            )
            is not None
            and performance_protocol.get("code_revision")
            == operational_protocol.get("code_revision"),
        ),
        _check(
            "offline_performance_reproducibility_protocol",
            {
                "schema_version": performance_reproducibility.get(
                    "schema_version"
                ),
                "method": performance_reproducibility.get("method"),
                "source_system": performance_protocol.get("source_system"),
                "minimum_trials": performance_protocol.get("minimum_trials"),
                "trial_count": performance_protocol.get("trial_count"),
                "verification_method": performance_protocol.get(
                    "verification_method"
                ),
                "threshold": performance_protocol.get(
                    "acceptance_threshold_ms_p95"
                ),
                "all_trials_must_pass": performance_protocol.get(
                    "all_trials_must_pass"
                ),
                "host_identifier_included": performance_protocol.get(
                    "host_identifier_included"
                ),
                "environment_sha256": performance_protocol.get(
                    "environment_sha256"
                ),
            },
            "fixed three-or-more-trial, all-pass, path-free 50ms protocol",
            performance_reproducibility.get("schema_version") == 1
            and performance_reproducibility.get("method")
            == "istina_offline_performance_repeatability_v1"
            and performance_protocol.get("source_system") == "istina"
            and int(performance_protocol.get("minimum_trials") or 0) == 3
            and int(performance_protocol.get("trial_count") or 0)
            == len(performance_trials)
            and len(performance_trials) >= 3
            and performance_protocol.get("verification_method")
            == "overall_nearest_rank_p95_all_replay_operations_v1"
            and performance_protocol.get("acceptance_threshold_ms_p95") == 50.0
            and performance_protocol.get("all_trials_must_pass") is True
            and performance_protocol.get("host_identifier_included") is False
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(performance_protocol.get("environment_sha256") or ""),
            )
            is not None,
        ),
        _check(
            "offline_performance_reproducibility_trials",
            {
                "trial_count": len(performance_trials),
                "unique_ids": len({item.get("trial_id") for item in performance_trials}),
                "unique_hashes": len({item.get("source_sha256") for item in performance_trials}),
                "passing": sum(item.get("verified") is True for item in performance_trials),
            },
            "three-or-more unique, exact-schema, 64-hex, passing trials",
            len(performance_trials) >= 3
            and all(
                set(item)
                == {
                    "trial_id",
                    "source_sha256",
                    "verified",
                    "latency_ms_p95",
                    "threshold_margin_ms",
                    "throughput_mentions_per_second",
                    "iteration_p95_minimum_ms",
                    "iteration_p95_median_ms",
                    "iteration_p95_maximum_ms",
                    "passing_iterations",
                    "total_iterations",
                }
                and re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",
                    str(item.get("trial_id") or ""),
                )
                is not None
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(item.get("source_sha256") or ""),
                )
                is not None
                and item.get("verified") is True
                and isinstance(item.get("latency_ms_p95"), (int, float))
                and not isinstance(item.get("latency_ms_p95"), bool)
                and math.isfinite(float(item["latency_ms_p95"]))
                and 0.0 <= float(item["latency_ms_p95"]) <= 50.0
                for item in performance_trials
            )
            and len({item["trial_id"] for item in performance_trials})
            == len(performance_trials)
            and len({item["source_sha256"] for item in performance_trials})
            == len(performance_trials),
        ),
        _check(
            "offline_performance_reproducibility_summary",
            performance_summary,
            "all trials pass and combined operations equal trial count times canonical operations",
            performance_summary.get("verified") is True
            and performance_summary.get("passing_trials")
            == performance_summary.get("trial_count")
            == len(performance_trials)
            and performance_summary.get("failed_trials") == 0
            and performance_summary.get("combined_replay_operations")
            == len(performance_trials)
            * int(
                (
                    (operational.get("operational_validation") or {}).get(
                        "offline_load_test"
                    )
                    or {}
                ).get("load_operations")
                or 0
            ),
        ),
        _check(
            "offline_performance_reproducibility_metrics",
            performance_metrics,
            "metrics recomputed from the exact ordered trial p95 values and maximum <=50ms",
            bool(performance_trials)
            and performance_metrics.get("trial_p95_ms")
            == [item["latency_ms_p95"] for item in performance_trials]
            and performance_metrics.get("trial_p95_minimum_ms")
            == min(item["latency_ms_p95"] for item in performance_trials)
            and performance_metrics.get("trial_p95_median_ms")
            == _nearest_rank_percentile(
                [item["latency_ms_p95"] for item in performance_trials],
                0.50,
            )
            and performance_metrics.get("trial_p95_maximum_ms")
            == max(item["latency_ms_p95"] for item in performance_trials)
            and performance_metrics.get("trial_p95_range_ms")
            == max(item["latency_ms_p95"] for item in performance_trials)
            - min(item["latency_ms_p95"] for item in performance_trials)
            and float(performance_metrics.get("trial_p95_maximum_ms") or math.inf)
            <= 50.0,
        ),
        _check(
            "offline_performance_reproducibility_non_release",
            performance_reproducibility.get("release_constraints"),
            {
                "repeated_operations_are_distinct_gold": False,
                "write_enabled_replacement_authorized": False,
            },
        ),
        _check("temporal_total", temporal_stats.get("total"), gold_temporal.get("test_mentions")),
        _check("temporal_existing", temporal_stats.get("existing_gold"), gold_temporal.get("existing_mentions")),
        _check("temporal_new", temporal_stats.get("new_gold"), gold_temporal.get("new_mentions")),
        _check("temporal_paper_overlap", gold_temporal.get("paper_overlap"), 0),
        _check("holdout_total", holdout_stats.get("total"), gold_holdout.get("test_mentions")),
        _check("holdout_existing", holdout_stats.get("existing_gold"), gold_holdout.get("existing_mentions")),
        _check("holdout_new", holdout_stats.get("new_gold"), gold_holdout.get("new_mentions")),
        _check(
            "holdout_is_diagnostic",
            gold_holdout.get("paper_overlap"),
            "greater than zero",
            int(gold_holdout.get("paper_overlap") or 0) > 0,
        ),
        _check("gate_total_mentions", _gate_observed(gate, "total_mentions"), temporal_stats.get("total")),
        _check("gate_existing_mentions", _gate_observed(gate, "existing_mentions"), temporal_stats.get("existing_gold")),
        _check("gate_new_mentions", _gate_observed(gate, "new_mentions"), temporal_stats.get("new_gold")),
        _check("gate_merge_precision", _gate_observed(gate, "merge_precision"), temporal_metrics.get("precision")),
        _check("gate_existing_recall", _gate_observed(gate, "existing_recall"), temporal_metrics.get("existing_recall")),
        _check("gate_auto_accuracy", _gate_observed(gate, "auto_accuracy"), temporal_metrics.get("auto_accuracy")),
        _check("gate_unknown_rate", _gate_observed(gate, "unknown_rate"), temporal_metrics.get("unknown_rate")),
        _check("gate_wrong_merge_rate", _gate_observed(gate, "wrong_merge_rate"), temporal_metrics.get("wrong_merge_rate")),
        _check(
            "superseded_public_source_guard",
            public_validation.get("artifact_status"),
            "superseded_for_istina_claims",
            public_validation.get("artifact_status") == "superseded_for_istina_claims"
            and public_validation.get("release_eligible") is False
            and "advisor_istina_default" not in public_results
            and "advisor_istina_raw_export_diagnostic_superseded" in public_results
            and (public_validation.get("release_verdict") or {}).get("classification")
            == "historical_non_release_diagnostic",
        ),
        _check(
            "retired_source_input_declarations_present",
            bool(
                public_validation.get("source_base_commit")
                and (((public_validation.get("inputs") or {}).get(
                    "openalex_confirmation_mentions"
                ) or {}).get("sha256"))
                and (((public_validation.get("inputs") or {}).get(
                    "openalex_confirmation_metadata"
                ) or {}).get("sha256"))
                and (((public_validation.get("inputs") or {}).get(
                    "aminer_kdd18_archive"
                ) or {}).get("sha256"))
            ),
            True,
        ),
        _check(
            "openalex_dataset_sha256",
            sorted({
                str(openalex_default_protocol.get("dataset_sha256") or ""),
                str(openalex_rescue_protocol.get("dataset_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "openalex_confirmation_mentions"
                    ) or {}).get("sha256")
                    or ""
                ),
            }),
            "one non-empty hash",
            len({
                str(openalex_default_protocol.get("dataset_sha256") or ""),
                str(openalex_rescue_protocol.get("dataset_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "openalex_confirmation_mentions"
                    ) or {}).get("sha256")
                    or ""
                ),
            } - {""}) == 1,
        ),
        _check(
            "openalex_metadata_sha256",
            sorted({
                str(openalex_default_protocol.get("metadata_sha256") or ""),
                str(openalex_rescue_protocol.get("metadata_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "openalex_confirmation_metadata"
                    ) or {}).get("sha256")
                    or ""
                ),
            }),
            "one non-empty hash",
            len({
                str(openalex_default_protocol.get("metadata_sha256") or ""),
                str(openalex_rescue_protocol.get("metadata_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "openalex_confirmation_metadata"
                    ) or {}).get("sha256")
                    or ""
                ),
            } - {""}) == 1,
        ),
        _check(
            "openalex_complete_paper_split",
            [
                openalex_default_protocol.get("article_overlap"),
                openalex_rescue_protocol.get("article_overlap"),
            ],
            [0, 0],
        ),
        _check(
            "openalex_ablation_modes",
            [
                openalex_default_protocol.get("calibrated_candidate_rescue"),
                openalex_rescue_protocol.get("calibrated_candidate_rescue"),
            ],
            [False, True],
        ),
        _check(
            "openalex_ablation_population",
            [
                (openalex_default.get("stats") or {}).get("total"),
                (openalex_default.get("stats") or {}).get("existing_gold"),
                (openalex_default.get("stats") or {}).get("new_gold"),
            ],
            [
                (openalex_rescue.get("stats") or {}).get("total"),
                (openalex_rescue.get("stats") or {}).get("existing_gold"),
                (openalex_rescue.get("stats") or {}).get("new_gold"),
            ],
        ),
        _check(
            "openalex_rescue_in_domain_effect",
            {
                "default_precision": (openalex_default.get("metrics") or {}).get("precision"),
                "rescue_precision": (openalex_rescue.get("metrics") or {}).get("precision"),
                "default_recall": (openalex_default.get("metrics") or {}).get("existing_recall"),
                "rescue_recall": (openalex_rescue.get("metrics") or {}).get("existing_recall"),
            },
            "precision non-decreasing and recall increasing",
            (
                float((openalex_rescue.get("metrics") or {}).get("precision") or 0.0)
                >= float((openalex_default.get("metrics") or {}).get("precision") or 0.0)
                and float((openalex_rescue.get("metrics") or {}).get("existing_recall") or 0.0)
                > float((openalex_default.get("metrics") or {}).get("existing_recall") or 0.0)
            ),
        ),
        _check(
            "openalex_large_dataset_sha256",
            [
                openalex_large_default_protocol.get("dataset_sha256"),
                openalex_large_rescue_protocol.get("dataset_sha256"),
            ],
            "two identical non-empty hashes",
            bool(openalex_large_default_protocol.get("dataset_sha256"))
            and openalex_large_default_protocol.get("dataset_sha256")
            == openalex_large_rescue_protocol.get("dataset_sha256"),
        ),
        _check(
            "openalex_large_metadata_sha256",
            [
                openalex_large_default_protocol.get("metadata_sha256"),
                openalex_large_rescue_protocol.get("metadata_sha256"),
            ],
            "two identical non-empty hashes",
            bool(openalex_large_default_protocol.get("metadata_sha256"))
            and openalex_large_default_protocol.get("metadata_sha256")
            == openalex_large_rescue_protocol.get("metadata_sha256"),
        ),
        _check(
            "openalex_large_source_declaration",
            {
                "source": openalex_large_default_protocol.get("source"),
                "gold_label": openalex_large_default_protocol.get("gold_label"),
                "sample_works": (
                    (openalex_large_default_protocol.get("metadata") or {})
                    .get("request", {})
                    .get("sample_works")
                ),
                "mentions": (
                    (openalex_large_default_protocol.get("metadata") or {})
                    .get("counts", {})
                    .get("mentions")
                ),
            },
            {
                "source": "OpenAlex API",
                "gold_label": "OpenAlex author ID (evaluation only)",
                "sample_works": 10_000,
                "mentions": 28_361,
            },
        ),
        _check(
            "openalex_large_complete_paper_split",
            [
                openalex_large_default_protocol.get("article_overlap"),
                openalex_large_rescue_protocol.get("article_overlap"),
            ],
            [0, 0],
        ),
        _check(
            "openalex_large_ablation_modes",
            [
                openalex_large_default_protocol.get(
                    "calibrated_candidate_rescue"
                ),
                openalex_large_rescue_protocol.get(
                    "calibrated_candidate_rescue"
                ),
            ],
            [False, True],
        ),
        _check(
            "openalex_large_ablation_population",
            [
                (openalex_large_default.get("stats") or {}).get("total"),
                (openalex_large_default.get("stats") or {}).get("existing_gold"),
                (openalex_large_default.get("stats") or {}).get("new_gold"),
            ],
            [
                (openalex_large_rescue.get("stats") or {}).get("total"),
                (openalex_large_rescue.get("stats") or {}).get("existing_gold"),
                (openalex_large_rescue.get("stats") or {}).get("new_gold"),
            ],
        ),
        _check(
            "openalex_large_minimum_scale",
            (openalex_large_default.get("stats") or {}).get("total"),
            ">=10000",
            int((openalex_large_default.get("stats") or {}).get("total") or 0)
            >= 10_000,
        ),
        _check(
            "openalex_large_rescue_negative_transfer_reproduced",
            {
                "default_precision": (
                    (openalex_large_default.get("metrics") or {}).get("precision")
                ),
                "rescue_precision": (
                    (openalex_large_rescue.get("metrics") or {}).get("precision")
                ),
                "default_recall": (
                    (openalex_large_default.get("metrics") or {}).get(
                        "existing_recall"
                    )
                ),
                "rescue_recall": (
                    (openalex_large_rescue.get("metrics") or {}).get(
                        "existing_recall"
                    )
                ),
                "default_wrong_merge": (
                    (openalex_large_default.get("stats") or {}).get("wrong_merge")
                ),
                "rescue_wrong_merge": (
                    (openalex_large_rescue.get("stats") or {}).get("wrong_merge")
                ),
            },
            "recall higher, precision lower, and wrong merges higher",
            (
                float(
                    (openalex_large_rescue.get("metrics") or {}).get(
                        "existing_recall"
                    )
                    or 0.0
                )
                > float(
                    (openalex_large_default.get("metrics") or {}).get(
                        "existing_recall"
                    )
                    or 0.0
                )
                and float(
                    (openalex_large_rescue.get("metrics") or {}).get("precision")
                    or 0.0
                )
                < float(
                    (openalex_large_default.get("metrics") or {}).get("precision")
                    or 0.0
                )
                and int(
                    (openalex_large_rescue.get("stats") or {}).get("wrong_merge")
                    or 0
                )
                > int(
                    (openalex_large_default.get("stats") or {}).get("wrong_merge")
                    or 0
                )
            ),
        ),
        _check(
            "aminer_archive_sha256",
            sorted({
                str(aminer_default_protocol.get("archive_sha256") or ""),
                str(aminer_rescue_protocol.get("archive_sha256") or ""),
                str(aminer_full_protocol.get("archive_sha256") or ""),
                str(aminer_full_rescue_protocol.get("archive_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "aminer_kdd18_archive"
                    ) or {}).get("sha256")
                    or ""
                ),
            }),
            "one non-empty hash",
            len({
                str(aminer_default_protocol.get("archive_sha256") or ""),
                str(aminer_rescue_protocol.get("archive_sha256") or ""),
                str(aminer_full_protocol.get("archive_sha256") or ""),
                str(aminer_full_rescue_protocol.get("archive_sha256") or ""),
                str(
                    ((public_validation.get("inputs") or {}).get(
                        "aminer_kdd18_archive"
                    ) or {}).get("sha256")
                    or ""
                ),
            } - {""}) == 1,
        ),
        _check(
            "aminer_extracted_file_hashes",
            [
                aminer_default_protocol.get("labels_sha256"),
                aminer_default_protocol.get("publications_sha256"),
                aminer_full_protocol.get("labels_sha256"),
                aminer_full_protocol.get("publications_sha256"),
            ],
            [
                aminer_rescue_protocol.get("labels_sha256"),
                aminer_rescue_protocol.get("publications_sha256"),
                aminer_full_rescue_protocol.get("labels_sha256"),
                aminer_full_rescue_protocol.get("publications_sha256"),
            ],
        ),
        _check(
            "aminer_current_full_protocol",
            [
                aminer_full_protocol.get("label_split"),
                aminer_full_protocol.get("start_name"),
                aminer_full_protocol.get("selected_names"),
                aminer_full_protocol.get("article_overlap"),
                aminer_full_protocol.get("calibrated_candidate_rescue"),
                (aminer_full_current.get("stats") or {}).get("total"),
            ],
            ["test_100", 0, 100, 0, False, 6412],
        ),
        _check(
            "aminer_current_full_rescue_protocol",
            [
                aminer_full_rescue_protocol.get("label_split"),
                aminer_full_rescue_protocol.get("start_name"),
                aminer_full_rescue_protocol.get("selected_names"),
                aminer_full_rescue_protocol.get("article_overlap"),
                aminer_full_rescue_protocol.get("calibrated_candidate_rescue"),
                (aminer_full_rescue_current.get("stats") or {}).get("total"),
            ],
            ["test_100", 0, 100, 0, True, 6412],
        ),
        _check(
            "aminer_current_full_ablation_population",
            [
                (aminer_full_current.get("stats") or {}).get("total"),
                (aminer_full_current.get("stats") or {}).get("existing_gold"),
                (aminer_full_current.get("stats") or {}).get("new_gold"),
            ],
            [
                (aminer_full_rescue_current.get("stats") or {}).get("total"),
                (aminer_full_rescue_current.get("stats") or {}).get(
                    "existing_gold"
                ),
                (aminer_full_rescue_current.get("stats") or {}).get("new_gold"),
            ],
        ),
        _check(
            "aminer_full_rescue_negative_transfer_reproduced",
            {
                "default_precision": (
                    (aminer_full_current.get("metrics") or {}).get("precision")
                ),
                "rescue_precision": (
                    (aminer_full_rescue_current.get("metrics") or {}).get(
                        "precision"
                    )
                ),
                "default_recall": (
                    (aminer_full_current.get("metrics") or {}).get(
                        "existing_recall"
                    )
                ),
                "rescue_recall": (
                    (aminer_full_rescue_current.get("metrics") or {}).get(
                        "existing_recall"
                    )
                ),
                "default_wrong_merge": (
                    (aminer_full_current.get("stats") or {}).get("wrong_merge")
                ),
                "rescue_wrong_merge": (
                    (aminer_full_rescue_current.get("stats") or {}).get(
                        "wrong_merge"
                    )
                ),
            },
            "recall higher, precision lower, and wrong merges higher",
            (
                float(
                    (aminer_full_rescue_current.get("metrics") or {}).get(
                        "existing_recall"
                    )
                    or 0.0
                )
                > float(
                    (aminer_full_current.get("metrics") or {}).get(
                        "existing_recall"
                    )
                    or 0.0
                )
                and float(
                    (aminer_full_rescue_current.get("metrics") or {}).get(
                        "precision"
                    )
                    or 0.0
                )
                < float(
                    (aminer_full_current.get("metrics") or {}).get("precision")
                    or 0.0
                )
                and int(
                    (aminer_full_rescue_current.get("stats") or {}).get(
                        "wrong_merge"
                    )
                    or 0
                )
                > int(
                    (aminer_full_current.get("stats") or {}).get("wrong_merge")
                    or 0
                )
            ),
        ),
        _check(
            "aminer_current_bounded_protocol",
            [
                aminer_default_protocol.get("label_split"),
                aminer_default_protocol.get("start_name"),
                aminer_default_protocol.get("selected_names"),
                aminer_default_protocol.get("article_overlap"),
                aminer_rescue_protocol.get("label_split"),
                aminer_rescue_protocol.get("start_name"),
                aminer_rescue_protocol.get("selected_names"),
                aminer_rescue_protocol.get("article_overlap"),
            ],
            ["test_100", 0, 10, 0, "test_100", 0, 10, 0],
        ),
        _check(
            "aminer_ablation_modes",
            [
                aminer_default_protocol.get("calibrated_candidate_rescue"),
                aminer_rescue_protocol.get("calibrated_candidate_rescue"),
            ],
            [False, True],
        ),
        _check(
            "aminer_ablation_population",
            [
                (aminer_default_current.get("stats") or {}).get("total"),
                (aminer_default_current.get("stats") or {}).get("existing_gold"),
                (aminer_default_current.get("stats") or {}).get("new_gold"),
            ],
            [
                (aminer_rescue_current.get("stats") or {}).get("total"),
                (aminer_rescue_current.get("stats") or {}).get("existing_gold"),
                (aminer_rescue_current.get("stats") or {}).get("new_gold"),
            ],
        ),
        _check(
            "aminer_rescue_negative_transfer_reproduced",
            {
                "default_precision": (aminer_default_current.get("metrics") or {}).get("precision"),
                "rescue_precision": (aminer_rescue_current.get("metrics") or {}).get("precision"),
                "default_wrong_merge": (aminer_default_current.get("stats") or {}).get("wrong_merge"),
                "rescue_wrong_merge": (aminer_rescue_current.get("stats") or {}).get("wrong_merge"),
            },
            "rescue precision lower and wrong merges higher",
            (
                float((aminer_rescue_current.get("metrics") or {}).get("precision") or 0.0)
                < float((aminer_default_current.get("metrics") or {}).get("precision") or 0.0)
                and int((aminer_rescue_current.get("stats") or {}).get("wrong_merge") or 0)
                > int((aminer_default_current.get("stats") or {}).get("wrong_merge") or 0)
            ),
        ),
        _check(
            "gate_summary_consistent",
            (gate.get("summary") or {}).get("total"),
            len(gate.get("checks") or []),
        ),
    ]
    failures = [check for check in checks if not check["passed"]]

    quality_rows = [
        _quality_row(
            "ISTINA advisor export",
            "strict temporal primary",
            temporal,
            gold_temporal.get("paper_overlap"),
            "temporal",
        ),
        _quality_row(
            "ISTINA advisor export",
            "per-author diagnostic only",
            holdout,
            gold_holdout.get("paper_overlap"),
            "holdout",
        ),
        _quality_row(
            "OpenAlex ORCID-blind confirmation",
            "current-runtime public confirmation",
            openalex_default,
            openalex_default_protocol.get("article_overlap"),
            "openalex_default",
        ),
        _quality_row(
            "OpenAlex 10,000-work sample",
            "current-runtime large cross-domain stress",
            openalex_large_default,
            openalex_large_default_protocol.get("article_overlap"),
            "openalex_large_default",
        ),
        _quality_row(
            "AMiner KDD'18 test_100",
            "current-runtime complete public transfer stress",
            aminer_full_current,
            aminer_full_protocol.get("article_overlap"),
            "aminer_full_current",
        ),
    ]
    openalex_ablation = [
        {
            "configuration": "production default",
            "calibrated_candidate_rescue": False,
            **dict(openalex_default.get("metrics") or {}),
            "wrong_merge": (openalex_default.get("stats") or {}).get("wrong_merge"),
        },
        {
            "configuration": "in-domain rescue ablation",
            "calibrated_candidate_rescue": True,
            **dict(openalex_rescue.get("metrics") or {}),
            "wrong_merge": (openalex_rescue.get("stats") or {}).get("wrong_merge"),
        },
    ]
    openalex_large_ablation = [
        {
            "configuration": "production default",
            "calibrated_candidate_rescue": False,
            **dict(openalex_large_default.get("metrics") or {}),
            "wrong_merge": (
                (openalex_large_default.get("stats") or {}).get("wrong_merge")
            ),
            "test_mentions": (
                (openalex_large_default.get("stats") or {}).get("total")
            ),
        },
        {
            "configuration": "OpenAlex rescue ablation",
            "calibrated_candidate_rescue": True,
            **dict(openalex_large_rescue.get("metrics") or {}),
            "wrong_merge": (
                (openalex_large_rescue.get("stats") or {}).get("wrong_merge")
            ),
            "test_mentions": (
                (openalex_large_rescue.get("stats") or {}).get("total")
            ),
        },
    ]
    aminer_current_ablation = [
        {
            "configuration": "production default",
            "calibrated_candidate_rescue": False,
            **dict(aminer_default_current.get("metrics") or {}),
            "wrong_merge": (aminer_default_current.get("stats") or {}).get("wrong_merge"),
            "test_mentions": (aminer_default_current.get("stats") or {}).get("total"),
        },
        {
            "configuration": "OpenAlex rescue cross-domain ablation",
            "calibrated_candidate_rescue": True,
            **dict(aminer_rescue_current.get("metrics") or {}),
            "wrong_merge": (aminer_rescue_current.get("stats") or {}).get("wrong_merge"),
            "test_mentions": (aminer_rescue_current.get("stats") or {}).get("total"),
        },
    ]
    aminer_full_ablation = [
        {
            "configuration": "production default",
            "calibrated_candidate_rescue": False,
            **dict(aminer_full_current.get("metrics") or {}),
            "wrong_merge": (
                (aminer_full_current.get("stats") or {}).get("wrong_merge")
            ),
            "test_mentions": (aminer_full_current.get("stats") or {}).get("total"),
        },
        {
            "configuration": "OpenAlex rescue cross-domain ablation",
            "calibrated_candidate_rescue": True,
            **dict(aminer_full_rescue_current.get("metrics") or {}),
            "wrong_merge": (
                (aminer_full_rescue_current.get("stats") or {}).get("wrong_merge")
            ),
            "test_mentions": (
                (aminer_full_rescue_current.get("stats") or {}).get("total")
            ),
        },
    ]
    temporal_legacy = dict(temporal.get("legacy_shadow") or {})
    holdout_legacy = dict(holdout.get("legacy_shadow") or {})
    live_diagnostic_p = _mcnemar_exact_two_sided(
        live_diagnostic_paired["runtime_only_correct"],
        live_diagnostic_paired["legacy_only_correct"],
    )
    frozen_paired = dict(holdout_legacy.get("paired_table") or {})
    legacy_service_drift = {
        "observed": (
            live_diagnostic_stats.get("legacy_correct")
            != holdout_legacy.get("legacy_correct")
            or live_diagnostic_paired != frozen_paired
        ),
        "framework_correct_frozen": holdout_legacy.get("runtime_correct"),
        "framework_correct_current_live": live_diagnostic_stats.get(
            "runtime_correct"
        ),
        "legacy_correct_frozen": holdout_legacy.get("legacy_correct"),
        "legacy_correct_current_live": live_diagnostic_stats.get(
            "legacy_correct"
        ),
        "legacy_correct_delta": (
            int(live_diagnostic_stats.get("legacy_correct") or 0)
            - int(holdout_legacy.get("legacy_correct") or 0)
        ),
        "paired_table_frozen": frozen_paired,
        "paired_table_current_live": live_diagnostic_paired,
        "current_live_generated_at": live_diagnostic.get("generated_at"),
        "interpretation": (
            "current incumbent observations differ from the frozen comparison; "
            "report both and do not overwrite the frozen baseline"
        ),
    }
    legacy_comparisons = [
        {
            "protocol_role": "strict temporal primary",
            **temporal_legacy,
            "statistically_significant_at_0_05": bool(
                temporal_legacy.get("mcnemar_exact_two_sided_p") is not None
                and temporal_legacy.get("mcnemar_exact_two_sided_p") < 0.05
            ),
        },
        {
            "protocol_role": "per-author diagnostic only",
            **holdout_legacy,
            "statistically_significant_at_0_05": bool(
                holdout_legacy.get("mcnemar_exact_two_sided_p") is not None
                and holdout_legacy.get("mcnemar_exact_two_sided_p") < 0.05
            ),
        },
        {
            "protocol_role": "per-author current-service live diagnostic only",
            "n": len(live_diagnostic_records),
            "paired_table": live_diagnostic_paired,
            "runtime_correct": live_diagnostic_stats.get("runtime_correct"),
            "legacy_correct": live_diagnostic_stats.get("legacy_correct"),
            "mcnemar_exact_two_sided_p": live_diagnostic_p,
            "statistically_significant_at_0_05": live_diagnostic_p < 0.05,
        },
    ]
    load = dict(
        ((operational.get("operational_validation") or {}).get("offline_load_test"))
        or {}
    )
    live_stats = dict(live.get("stats") or {})
    live_metrics = dict(live.get("metrics") or {})
    live_safety = dict(live.get("safety") or {})
    live_diagnostic_metrics = dict(live_diagnostic.get("metrics") or {})
    operational_summary = {
        "offline_load_verified": load.get("verified"),
        "offline_load_operations": load.get("load_operations"),
        "offline_load_p95_ms": load.get("latency_ms_p95"),
        "offline_throughput_mentions_per_second": load.get("throughput_mentions_per_second"),
        "deterministic_hash_mismatches": load.get("deterministic_hash_mismatches"),
        "runtime_safety_contract_verified": bool(
            (((bundle.get("operational_evidence") or {}).get("runtime_safety_contract_verified") or {}).get("verified"))
        ),
        "rollback_verified": bool(
            (((bundle.get("operational_evidence") or {}).get("rollback_verified") or {}).get("verified"))
        ),
        "drift_fault_test_verified": bool(
            (((bundle.get("operational_evidence") or {}).get("drift_monitor_test_verified") or {}).get("verified"))
        ),
        "live_shadow_mentions": live_stats.get("attempted_mentions"),
        "live_shadow_service_errors": live_stats.get("service_errors"),
        "live_shadow_authorized_commands": live_stats.get("authorized_commands"),
        "live_shadow_p95_ms": live_metrics.get("paper_round_trip_latency_ms_p95"),
        "live_audit_chain_verified": bool(
            ((live_safety.get("durable_audit_chain") or {}).get("verified"))
        ),
        "live_audit_retained": bool(
            ((live_safety.get("durable_audit_chain") or {}).get("retained"))
        ),
        "live_diagnostic_mentions": live_diagnostic_stats.get(
            "attempted_mentions"
        ),
        "live_diagnostic_papers": live_diagnostic_protocol.get(
            "paper_requests"
        ),
        "live_diagnostic_framework_correct": live_diagnostic_stats.get(
            "runtime_correct"
        ),
        "live_diagnostic_legacy_correct": live_diagnostic_stats.get(
            "legacy_correct"
        ),
        "live_diagnostic_service_errors": live_diagnostic_stats.get(
            "service_errors"
        ),
        "live_diagnostic_authorized_commands": live_diagnostic_stats.get(
            "authorized_commands"
        ),
        "live_diagnostic_p95_ms": live_diagnostic_metrics.get(
            "paper_round_trip_latency_ms_p95"
        ),
        "legacy_service_drift_observed": legacy_service_drift["observed"],
        "legacy_service_correct_delta": legacy_service_drift[
            "legacy_correct_delta"
        ],
        "online_canary_requests": online_canary_stats.get("requests"),
        "online_canary_errors": online_canary_stats.get("errors"),
        "online_canary_p95_ms": online_canary_metrics.get("latency_ms_p95"),
        "online_canary_concurrency": online_canary_protocol.get("concurrency"),
        "online_canary_classification": online_canary_safety.get(
            "evidence_classification"
        ),
        "offline_repeatability_verified": performance_summary.get("verified"),
        "offline_repeatability_trials": performance_summary.get("trial_count"),
        "offline_repeatability_combined_operations": performance_summary.get(
            "combined_replay_operations"
        ),
        "offline_repeatability_p95_median_ms": performance_metrics.get(
            "trial_p95_median_ms"
        ),
        "offline_repeatability_p95_maximum_ms": performance_metrics.get(
            "trial_p95_maximum_ms"
        ),
        "offline_repeatability_p95_range_ms": performance_metrics.get(
            "trial_p95_range_ms"
        ),
    }
    supported_claims = [
        {
            "id": "istina_zero_observed_wrong_merges_limited_sample",
            "statement": (
                "The cleaned strict-temporal ISTINA sample has no observed wrong "
                f"merge, but contains only {temporal_stats.get('existing_gold')} "
                f"known-author cases and {temporal_stats.get('merge')} automatic "
                "merges."
            ),
            "sources": ["temporal", "gold"],
        },
        {
            "id": "legacy_advantage_not_established",
            "statement": (
                f"The cleaned {holdout_legacy.get('n')}-case diagnostic compares "
                f"the independent framework at {holdout_legacy.get('runtime_correct')} "
                f"correct with the legacy service at {holdout_legacy.get('legacy_correct')} "
                "correct. A fresh read-only live run keeps the framework at "
                f"{live_diagnostic_stats.get('runtime_correct')} correct while the "
                f"current legacy service reaches {live_diagnostic_stats.get('legacy_correct')} "
                "correct; neither paired comparison establishes a statistically "
                "significant advantage."
            ),
            "sources": ["holdout", "live_diagnostic"],
        },
        {
            "id": "bounded_online_no_write_connectivity",
            "statement": (
                "A five-mention real-service smoke demonstrates bounded no-write "
                "connectivity. A separate four-request, concurrency-two online "
                "load canary completes with zero errors and zero writes, but its "
                "user-authorized scope and sub-threshold volume make it "
                "non-release evidence."
            ),
            "sources": ["live", "online_canary"],
        },
        {
            "id": "offline_performance_repeatability",
            "statement": (
                "Three sequential frozen-revision offline trials, totaling "
                f"{performance_summary.get('combined_replay_operations')} replay "
                "operations, all satisfy the unchanged 50 ms all-operation p95 "
                f"limit; trial median/max p95 are {float(performance_metrics.get('trial_p95_median_ms') or 0.0):.2f}/"
                f"{float(performance_metrics.get('trial_p95_maximum_ms') or 0.0):.2f} ms. "
                "Repeated operations are load evidence, not additional gold."
            ),
            "sources": ["performance_reproducibility"],
        },
        {
            "id": "diagnostic_online_comparison_current",
            "statement": (
                "A separate 38-mention, 14-paper real-service diagnostic "
                f"reproduces the framework score at {live_diagnostic_stats.get('runtime_correct')} "
                f"correct, while the current legacy result is {live_diagnostic_stats.get('legacy_correct')} "
                "correct rather than the frozen baseline. It has zero service "
                "errors and zero authorized commands; its overlapping per-author "
                "split and sub-threshold volume make it non-release evidence."
            ),
            "sources": ["holdout", "live_diagnostic"],
        },
        {
            "id": "legacy_service_output_drift_observed",
            "statement": (
                "The current live legacy-service outcome differs from the frozen "
                f"comparison by {legacy_service_drift['legacy_correct_delta']:+d} "
                "correct cases and has a different paired table. The frozen and "
                "current results are therefore reported separately."
            ),
            "sources": ["holdout", "live_diagnostic"],
        },
        {
            "id": "public_negative_transfer",
            "statement": (
                "The rescue improves recall without reducing precision on the "
                "current OpenAlex confirmation, but lowers precision and increases "
                "wrong merges on both the 27,430-mention OpenAlex stress ablation "
                "and the complete 6,412-mention AMiner ablation. Universal "
                "superiority is therefore unsupported."
            ),
            "sources": [
                "openalex_large_default",
                "openalex_large_rescue",
                "aminer_default_current",
                "aminer_rescue_current",
                "aminer_full_current",
                "aminer_full_rescue_current",
            ],
        },
        {
            "id": "write_release_not_authorized",
            "statement": (
                "The current machine gate does not authorize write-enabled ISTINA replacement."
            ),
            "sources": ["gate", "bundle"],
        },
    ]
    prohibited_claims = [
        "statistically significant superiority over the legacy ISTINA service",
        "universal author-disambiguation superiority",
        "release-scale online latency or availability",
        "write-enabled production replacement authorization",
    ]
    release_gaps = [
        {
            "name": failure.get("name"),
            "category": failure.get("category"),
            "observed": failure.get("observed"),
            "required": failure.get("required"),
        }
        for failure in gate.get("failures") or []
        if isinstance(failure, Mapping)
    ]
    core = {
        "integrity": {
            "verified": not failures,
            "summary": {
                "passed": len(checks) - len(failures),
                "failed": len(failures),
                "total": len(checks),
            },
            "checks": checks,
            "failures": failures,
        },
        "sources": {key: dict(value) for key, value in sources.items()},
        "dataset_identity": {
            "advisor_export_sha256": next(iter(dataset_hashes), None)
            if len(dataset_hashes) == 1 else None,
            "frozen_legacy_service_sha256": next(iter(service_hashes), None)
            if len(service_hashes) == 1 else None,
            "exact_duplicate_rows_removed": 52,
            "provenance_verified": bool((gold.get("provenance") or {}).get("verified")),
            "gold_readiness_passed": (gold.get("summary") or {}).get("passed"),
            "gold_readiness_total": (gold.get("summary") or {}).get("total"),
            "openalex_confirmation_sha256": openalex_default_protocol.get("dataset_sha256"),
            "openalex_metadata_sha256": openalex_default_protocol.get("metadata_sha256"),
            "openalex_large_sha256": openalex_large_default_protocol.get(
                "dataset_sha256"
            ),
            "openalex_large_metadata_sha256": openalex_large_default_protocol.get(
                "metadata_sha256"
            ),
            "aminer_archive_sha256": aminer_default_protocol.get("archive_sha256"),
            "aminer_labels_sha256": aminer_default_protocol.get("labels_sha256"),
            "aminer_publications_sha256": aminer_default_protocol.get("publications_sha256"),
            "retired_runtime_validation_source_commit": public_validation.get("source_base_commit"),
        },
        "quality_table": quality_rows,
        "openalex_ablation_table": openalex_ablation,
        "openalex_large_ablation_table": openalex_large_ablation,
        "aminer_full_ablation_table": aminer_full_ablation,
        "aminer_current_ablation_table": aminer_current_ablation,
        "legacy_comparison_table": legacy_comparisons,
        "legacy_service_drift": legacy_service_drift,
        "operational_summary": operational_summary,
        "supported_claims": supported_claims,
        "prohibited_claims": prohibited_claims,
        "release": {
            "release_ready": bool(gate.get("release_ready")),
            "passed": (gate.get("summary") or {}).get("passed"),
            "failed": (gate.get("summary") or {}).get("failed"),
            "total": (gate.get("summary") or {}).get("total"),
            "remaining_gaps": release_gaps,
        },
    }
    package_id = hashlib.sha256(_canonical_json(core).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "package_id": package_id,
        **core,
    }


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * float(value):.2f}%"


def _value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _passed(value: Any) -> str:
    return "passed" if bool(value) else "failed"


def render_markdown(package: Mapping[str, Any]) -> str:
    integrity = dict(package.get("integrity") or {})
    release = dict(package.get("release") or {})
    dataset = dict(package.get("dataset_identity") or {})
    lines = [
        "# ISTINA author-disambiguation empirical evidence package",
        "",
        f"Package ID: `{package.get('package_id')}`.",
        "",
        (
            "This package is internally consistent and machine-traceable for "
            "article use. It is not a "
            "write-enabled production authorization."
            if integrity.get("verified")
            else "This package failed integrity validation and must not be cited."
        ),
        "",
        "## Dataset and protocol status",
        "",
        f"- Advisor export SHA-256: `{dataset.get('advisor_export_sha256')}`",
        f"- Frozen legacy sample SHA-256: `{dataset.get('frozen_legacy_service_sha256')}`",
        f"- Exact duplicate author rows removed: {dataset.get('exact_duplicate_rows_removed')}",
        f"- Gold readiness: {dataset.get('gold_readiness_passed')}/{dataset.get('gold_readiness_total')}",
        f"- Verified ISTINA provenance: {str(dataset.get('provenance_verified')).lower()}",
        f"- OpenAlex confirmation SHA-256: `{dataset.get('openalex_confirmation_sha256')}`",
        f"- OpenAlex 10,000-work sample SHA-256: `{dataset.get('openalex_large_sha256')}`",
        f"- AMiner archive SHA-256: `{dataset.get('aminer_archive_sha256')}`",
        f"- Retired runtime-validation source commit: `{dataset.get('retired_runtime_validation_source_commit')}`",
        "",
        "## Quality results",
        "",
        "| Dataset | Protocol role | Test | Known | New | Paper overlap | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong-merge rate | p95 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in package.get("quality_table") or []:
        lines.append(
            "| {dataset} | {role} | {test} | {known} | {new} | {overlap} | "
            "{precision} | {recall} | {accuracy} | {unknown} | {wrong} | {p95} |".format(
                dataset=row.get("dataset"),
                role=row.get("protocol_role"),
                test=_value(row.get("test_mentions")),
                known=_value(row.get("existing_mentions")),
                new=_value(row.get("new_mentions")),
                overlap=_value(row.get("paper_overlap")),
                precision=_pct(row.get("merge_precision")),
                recall=_pct(row.get("existing_recall")),
                accuracy=_pct(row.get("automatic_accuracy")),
                unknown=_pct(row.get("unknown_rate")),
                wrong=_pct(row.get("wrong_merge_rate")),
                p95=(
                    "n/a"
                    if row.get("p95_latency_ms") is None
                    else f"{float(row.get('p95_latency_ms')):.2f}"
                ),
            )
        )
    lines.extend([
        "",
        "The OpenAlex and complete AMiner rows were rerun on the current runtime. "
        "All superseded ISTINA, OpenAlex, and AMiner result rows in "
        "`runtime_validation_20260719.json` are ignored.",
        "",
        "## OpenAlex in-domain rescue ablation",
        "",
        "| Configuration | Rescue enabled | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in package.get("openalex_ablation_table") or []:
        lines.append(
            "| {configuration} | {enabled} | {precision} | {recall} | {accuracy} | {unknown} | {wrong} | {p95:.2f} |".format(
                configuration=row.get("configuration"),
                enabled=str(row.get("calibrated_candidate_rescue")).lower(),
                precision=_pct(row.get("precision")),
                recall=_pct(row.get("existing_recall")),
                accuracy=_pct(row.get("auto_accuracy")),
                unknown=_pct(row.get("unknown_rate")),
                wrong=row.get("wrong_merge"),
                p95=float(row.get("latency_ms_p95") or 0.0),
            )
        )
    lines.extend([
        "",
        "## OpenAlex 10,000-work cross-domain stress ablation",
        "",
        "The complete-paper split contains 27,430 test mentions with zero "
        "publication overlap. This is public external validation, not ISTINA "
        "release evidence. The rescue result is retained as negative-transfer "
        "evidence.",
        "",
        "| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in package.get("openalex_large_ablation_table") or []:
        lines.append(
            "| {configuration} | {enabled} | {test} | {precision} | {recall} | {accuracy} | {unknown} | {wrong} | {p95:.2f} |".format(
                configuration=row.get("configuration"),
                enabled=str(row.get("calibrated_candidate_rescue")).lower(),
                test=row.get("test_mentions"),
                precision=_pct(row.get("precision")),
                recall=_pct(row.get("existing_recall")),
                accuracy=_pct(row.get("auto_accuracy")),
                unknown=_pct(row.get("unknown_rate")),
                wrong=row.get("wrong_merge"),
                p95=float(row.get("latency_ms_p95") or 0.0),
            )
        )
    lines.extend([
        "",
        "## AMiner complete current-runtime cross-domain ablation",
        "",
        "Both configurations use all 100 deterministic AMiner name blocks "
        "(6,412 test mentions) and zero publication overlap. The rescue run "
        "improves recall but causes lower precision and more wrong merges.",
        "",
        "| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in package.get("aminer_full_ablation_table") or []:
        lines.append(
            "| {configuration} | {enabled} | {test} | {precision} | {recall} | {accuracy} | {unknown} | {wrong} | {p95:.2f} |".format(
                configuration=row.get("configuration"),
                enabled=str(row.get("calibrated_candidate_rescue")).lower(),
                test=row.get("test_mentions"),
                precision=_pct(row.get("precision")),
                recall=_pct(row.get("existing_recall")),
                accuracy=_pct(row.get("auto_accuracy")),
                unknown=_pct(row.get("unknown_rate")),
                wrong=row.get("wrong_merge"),
                p95=float(row.get("latency_ms_p95") or 0.0),
            )
        )
    lines.extend([
        "",
        "## AMiner bounded consistency ablation",
        "",
        "This table uses the first 10 of 100 deterministic AMiner name blocks "
        "(679 test mentions). It is a bounded current-runtime ablation, not a "
        "replacement for the complete 6,412-mention current-runtime stress row.",
        "",
        "| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in package.get("aminer_current_ablation_table") or []:
        lines.append(
            "| {configuration} | {enabled} | {test} | {precision} | {recall} | {accuracy} | {unknown} | {wrong} | {p95:.2f} |".format(
                configuration=row.get("configuration"),
                enabled=str(row.get("calibrated_candidate_rescue")).lower(),
                test=row.get("test_mentions"),
                precision=_pct(row.get("precision")),
                recall=_pct(row.get("existing_recall")),
                accuracy=_pct(row.get("auto_accuracy")),
                unknown=_pct(row.get("unknown_rate")),
                wrong=row.get("wrong_merge"),
                p95=float(row.get("latency_ms_p95") or 0.0),
            )
        )
    lines.extend([
        "",
        "## Fair legacy-service comparison",
        "",
        (
            "Framework decisions are computed with legacy-service fallback "
            "disabled; incumbent outputs are retained only as paired observations."
        ),
        "",
        "| Protocol | Shared cases | Framework correct | Legacy correct | Exact McNemar p | Significant at 0.05 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in package.get("legacy_comparison_table") or []:
        lines.append(
            "| {role} | {n} | {runtime} | {legacy} | {p:.6f} | {significant} |".format(
                role=row.get("protocol_role"),
                n=row.get("n"),
                runtime=row.get("runtime_correct"),
                legacy=row.get("legacy_correct"),
                p=float(row.get("mcnemar_exact_two_sided_p") or 0.0),
                significant=str(row.get("statistically_significant_at_0_05")).lower(),
            )
        )
    drift = dict(package.get("legacy_service_drift") or {})
    lines.extend([
        "",
        (
            "Legacy-service result drift relative to the frozen comparison: "
            f"observed={str(bool(drift.get('observed'))).lower()}, frozen "
            f"legacy correct={drift.get('legacy_correct_frozen')}, current-live "
            f"legacy correct={drift.get('legacy_correct_current_live')} "
            f"(delta {int(drift.get('legacy_correct_delta') or 0):+d}); framework "
            f"correct remained {drift.get('framework_correct_current_live')}."
        ),
    ])
    operations = dict(package.get("operational_summary") or {})
    lines.extend([
        "",
        "## Operational evidence",
        "",
        f"- Offline no-write operations: {operations.get('offline_load_operations')}",
        f"- Offline load threshold verified: {_value(operations.get('offline_load_verified'))}",
        f"- Offline load p95: {float(operations.get('offline_load_p95_ms') or 0.0):.2f} ms",
        f"- Offline throughput: {float(operations.get('offline_throughput_mentions_per_second') or 0.0):.2f} mentions/s",
        f"- Deterministic mismatches: {operations.get('deterministic_hash_mismatches')}",
        f"- Runtime safety / rollback / drift fault tests: {_passed(operations.get('runtime_safety_contract_verified'))} / {_passed(operations.get('rollback_verified'))} / {_passed(operations.get('drift_fault_test_verified'))}",
        f"- Real-service shadow: {operations.get('live_shadow_mentions')} mentions, {operations.get('live_shadow_service_errors')} service errors, {operations.get('live_shadow_authorized_commands')} authorized commands",
        f"- Live paper-request p95: {float(operations.get('live_shadow_p95_ms') or 0.0):.2f} ms",
        f"- Live audit chain verified / retained: {_value(operations.get('live_audit_chain_verified'))} / {_value(operations.get('live_audit_retained'))}",
        (
            "- Real-service diagnostic replication: "
            f"{operations.get('live_diagnostic_mentions')} mentions across "
            f"{operations.get('live_diagnostic_papers')} papers, framework "
            f"{operations.get('live_diagnostic_framework_correct')} correct "
            f"versus legacy {operations.get('live_diagnostic_legacy_correct')} "
            f"correct, {operations.get('live_diagnostic_service_errors')} "
            "service errors, "
            f"{operations.get('live_diagnostic_authorized_commands')} "
            "authorized commands"
        ),
        f"- Diagnostic live paper-request p95: {float(operations.get('live_diagnostic_p95_ms') or 0.0):.2f} ms",
        (
            "- Online read-only load canary: "
            f"{operations.get('online_canary_requests')} requests at concurrency "
            f"{operations.get('online_canary_concurrency')}, "
            f"{operations.get('online_canary_errors')} errors, p95 "
            f"{float(operations.get('online_canary_p95_ms') or 0.0):.2f} ms, "
            f"classification={operations.get('online_canary_classification')}"
        ),
        (
            "- Offline performance repeatability: "
            f"verified={str(bool(operations.get('offline_repeatability_verified'))).lower()}, "
            f"{operations.get('offline_repeatability_trials')} trials / "
            f"{operations.get('offline_repeatability_combined_operations')} operations, "
            f"trial median/max p95 "
            f"{float(operations.get('offline_repeatability_p95_median_ms') or 0.0):.2f}/"
            f"{float(operations.get('offline_repeatability_p95_maximum_ms') or 0.0):.2f} ms"
        ),
        "",
        "## Article-safe interpretation",
        "",
    ])
    for claim in package.get("supported_claims") or []:
        lines.append(f"- {claim.get('statement')}")
    lines.extend([
        "",
        "Claims that remain prohibited:",
        "",
    ])
    for claim in package.get("prohibited_claims") or []:
        lines.append(f"- {claim}")
    lines.extend([
        "",
        "## Machine release gate",
        "",
        f"Result: **{release.get('passed')}/{release.get('total')} passed; `release_ready: {str(release.get('release_ready')).lower()}`.**",
        "",
        "| Missing check | Category | Observed | Required |",
        "|---|---|---:|---|",
    ])
    for gap in release.get("remaining_gaps") or []:
        lines.append(
            f"| {gap.get('name')} | {gap.get('category')} | {_value(gap.get('observed'))} | {_value(gap.get('required'))} |"
        )
    lines.extend([
        "",
        "## Source traceability",
        "",
        "| Source | File | SHA-256 |",
        "|---|---|---|",
    ])
    for key, source in sorted((package.get("sources") or {}).items()):
        lines.append(f"| {key} | `{source.get('name')}` | `{source.get('sha256')}` |")
    return "\n".join(lines) + "\n"


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--operational", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--live-diagnostic", type=Path, required=True)
    parser.add_argument("--online-canary", type=Path, required=True)
    parser.add_argument("--performance-reproducibility", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--openalex-default", type=Path, required=True)
    parser.add_argument("--openalex-rescue", type=Path, required=True)
    parser.add_argument("--openalex-large-default", type=Path, required=True)
    parser.add_argument("--openalex-large-rescue", type=Path, required=True)
    parser.add_argument("--aminer-full-current", type=Path, required=True)
    parser.add_argument("--aminer-full-rescue-current", type=Path, required=True)
    parser.add_argument("--aminer-default-current", type=Path, required=True)
    parser.add_argument("--aminer-rescue-current", type=Path, required=True)
    parser.add_argument("--public-validation", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "temporal": args.temporal,
        "holdout": args.holdout,
        "operational": args.operational,
        "gold": args.gold,
        "live": args.live,
        "live_diagnostic": args.live_diagnostic,
        "online_canary": args.online_canary,
        "performance_reproducibility": args.performance_reproducibility,
        "bundle": args.bundle,
        "gate": args.gate,
        "openalex_default": args.openalex_default,
        "openalex_rescue": args.openalex_rescue,
        "openalex_large_default": args.openalex_large_default,
        "openalex_large_rescue": args.openalex_large_rescue,
        "aminer_full_current": args.aminer_full_current,
        "aminer_full_rescue_current": args.aminer_full_rescue_current,
        "aminer_default_current": args.aminer_default_current,
        "aminer_rescue_current": args.aminer_rescue_current,
        "public_validation": args.public_validation,
    }
    documents = {key: _load(path) for key, path in paths.items()}
    sources = {
        key: {"name": path.name, "sha256": sha256_file(path)}
        for key, path in paths.items()
    }
    package = compose_paper_package(
        temporal=documents["temporal"],
        holdout=documents["holdout"],
        operational=documents["operational"],
        gold=documents["gold"],
        live=documents["live"],
        live_diagnostic=documents["live_diagnostic"],
        online_canary=documents["online_canary"],
        performance_reproducibility=documents["performance_reproducibility"],
        bundle=documents["bundle"],
        gate=documents["gate"],
        openalex_default=documents["openalex_default"],
        openalex_rescue=documents["openalex_rescue"],
        openalex_large_default=documents["openalex_large_default"],
        openalex_large_rescue=documents["openalex_large_rescue"],
        aminer_full_current=documents["aminer_full_current"],
        aminer_full_rescue_current=documents["aminer_full_rescue_current"],
        aminer_default_current=documents["aminer_default_current"],
        aminer_rescue_current=documents["aminer_rescue_current"],
        public_validation=documents["public_validation"],
        sources=sources,
    )
    if not package["integrity"]["verified"]:
        failed_names = ", ".join(
            failure["name"] for failure in package["integrity"]["failures"]
        )
        raise ValueError("paper evidence integrity failed: " + failed_names)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(package, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    args.output_markdown.write_text(render_markdown(package), encoding="utf-8")
    print(json.dumps({
        "output_json": str(args.output_json),
        "output_markdown": str(args.output_markdown),
        "package_id": package["package_id"],
        "integrity_checks": package["integrity"]["summary"],
        "release_ready": package["release"]["release_ready"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
