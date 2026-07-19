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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    temporal_stats = dict(temporal.get("stats") or {})
    holdout_stats = dict(holdout.get("stats") or {})
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
            ((gold_dataset.get("automatic_cleaning") or {}).get(
                "exact_duplicate_author_rows_removed"
            ))
            or 0
        ),
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
                )
            ),
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
    ]
    load = dict(
        ((operational.get("operational_validation") or {}).get("offline_load_test"))
        or {}
    )
    live_stats = dict(live.get("stats") or {})
    live_metrics = dict(live.get("metrics") or {})
    live_safety = dict(live.get("safety") or {})
    operational_summary = {
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
    }
    supported_claims = [
        {
            "id": "istina_zero_observed_wrong_merges_limited_sample",
            "statement": (
                "The cleaned strict-temporal ISTINA sample has no observed wrong "
                "merge, but contains only five known-author cases and one merge."
            ),
            "sources": ["temporal", "gold"],
        },
        {
            "id": "legacy_advantage_not_established",
            "statement": (
                "The cleaned 38-case diagnostic favors the framework 28 to 24, "
                "but the exact paired test is not statistically significant."
            ),
            "sources": ["holdout"],
        },
        {
            "id": "bounded_online_no_write_connectivity",
            "statement": (
                "A five-mention real-service smoke demonstrates bounded no-write "
                "connectivity, not release-scale online performance."
            ),
            "sources": ["live"],
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
    operations = dict(package.get("operational_summary") or {})
    lines.extend([
        "",
        "## Operational evidence",
        "",
        f"- Offline no-write operations: {operations.get('offline_load_operations')}",
        f"- Offline load p95: {float(operations.get('offline_load_p95_ms') or 0.0):.2f} ms",
        f"- Offline throughput: {float(operations.get('offline_throughput_mentions_per_second') or 0.0):.2f} mentions/s",
        f"- Deterministic mismatches: {operations.get('deterministic_hash_mismatches')}",
        f"- Runtime safety / rollback / drift fault tests: {_passed(operations.get('runtime_safety_contract_verified'))} / {_passed(operations.get('rollback_verified'))} / {_passed(operations.get('drift_fault_test_verified'))}",
        f"- Real-service shadow: {operations.get('live_shadow_mentions')} mentions, {operations.get('live_shadow_service_errors')} service errors, {operations.get('live_shadow_authorized_commands')} authorized commands",
        f"- Live paper-request p95: {float(operations.get('live_shadow_p95_ms') or 0.0):.2f} ms",
        f"- Live audit chain verified / retained: {_value(operations.get('live_audit_chain_verified'))} / {_value(operations.get('live_audit_retained'))}",
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
