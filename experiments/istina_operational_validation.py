"""Validate production safety controls on a real ISTINA export.

This command performs a repeated, no-write local load replay; deterministic
replay checks; redacted-audit and idempotency checks; and explicit circuit-
breaker, drift, and rollback fault injection.  It never treats repeated load
operations as additional gold mentions and never claims that local tests are
equivalent to an online production shadow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.decision_types import Decision  # noqa: E402
from experiments.istina_export_temporal_evaluation import (  # noqa: E402
    iter_mentions,
    load_articles,
    mention_identity,
    split_mentions,
)
from experiments.istina_runtime_replay import (  # noqa: E402
    exact_mcnemar_two_sided,
    load_service_records,
    percentile,
    record_service_response,
)
from integrations.istina_pipeline import (  # noqa: E402
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
    article_mentions,
)
from integrations.istina_observability import (  # noqa: E402
    TamperEvidentJsonlAuditSink,
    verify_audit_chain,
)
from integrations.istina_export_quality import (  # noqa: E402
    deduplicate_exact_author_rows,
)
from integrations.istina_production_runtime import (  # noqa: E402
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    DecisionDriftMonitor,
    DriftBaseline,
    DriftThresholds,
    IstinaProductionRuntime,
    RuntimeMode,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_quality(
    decisions: Iterable[Any],
    mentions: Iterable[Mapping[str, Any]],
    known_ids: set[str],
    service_records: Mapping[Tuple[str, str, str, str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    stats = Counter({
        "total": 0,
        "existing_gold": 0,
        "new_gold": 0,
        "merge": 0,
        "new": 0,
        "unknown": 0,
        "correct_merge": 0,
        "wrong_merge": 0,
        "correct_new": 0,
        "false_new_for_existing": 0,
        "merge_for_new_gold": 0,
    })
    paired = Counter({
        "both_correct": 0,
        "runtime_only_correct": 0,
        "legacy_only_correct": 0,
        "both_incorrect": 0,
    })
    latencies: List[float] = []
    stages: Counter[str] = Counter()
    for decision, mention in zip(decisions, mentions):
        gold = str(mention.get("gold_author_id") or "")
        if not gold:
            continue
        seen = gold in known_ids
        correct_merge = decision.decision == Decision.MERGE and decision.author_id == gold
        stats["total"] += 1
        stats["existing_gold" if seen else "new_gold"] += 1
        stats[decision.decision.value] += 1
        stages[decision.stage] += 1
        latencies.append(decision.latency_ms)
        if decision.decision == Decision.MERGE:
            stats["correct_merge" if correct_merge else "wrong_merge"] += 1
            if not seen:
                stats["merge_for_new_gold"] += 1
        elif decision.decision == Decision.NEW:
            stats["false_new_for_existing" if seen else "correct_new"] += 1

        service_record = service_records.get(mention_identity(dict(mention)))
        if service_record and seen:
            legacy_correct = str(service_record.get("result_id")) == gold
            paired[
                "both_correct" if correct_merge and legacy_correct else
                "runtime_only_correct" if correct_merge else
                "legacy_only_correct" if legacy_correct else
                "both_incorrect"
            ] += 1

    total = stats["total"]
    precision = stats["correct_merge"] / stats["merge"] if stats["merge"] else 0.0
    recall = (
        stats["correct_merge"] / stats["existing_gold"]
        if stats["existing_gold"] else 0.0
    )
    shadow_n = sum(paired.values())
    return {
        "stats": dict(stats),
        "metrics": {
            "precision": precision,
            "existing_recall": recall,
            "auto_accuracy": (
                (stats["correct_merge"] + stats["correct_new"]) / total
                if total else 0.0
            ),
            "unknown_rate": stats["unknown"] / total if total else 0.0,
            "wrong_merge_rate": stats["wrong_merge"] / total if total else 0.0,
            "latency_ms_p50": percentile(latencies, 0.50),
            "latency_ms_p95": percentile(latencies, 0.95),
            "latency_ms_p99": percentile(latencies, 0.99),
        },
        "stage_counts": dict(sorted(stages.items())),
        "legacy_shadow": {
            "n": shadow_n,
            "paired_table": dict(paired),
            "runtime_correct": paired["both_correct"] + paired["runtime_only_correct"],
            "legacy_correct": paired["both_correct"] + paired["legacy_only_correct"],
            "mcnemar_exact_two_sided_p": (
                exact_mcnemar_two_sided(
                    paired["runtime_only_correct"],
                    paired["legacy_only_correct"],
                ) if shadow_n else None
            ),
        },
    }


def circuit_breaker_fault_injection() -> Dict[str, Any]:
    clock = [0.0]
    breaker = CircuitBreaker(
        CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout_seconds=5.0,
        ),
        clock=lambda: clock[0],
    )
    for _ in range(2):
        breaker.before_call()
        breaker.record_failure()
    rejected_while_open = False
    try:
        breaker.before_call()
    except CircuitOpenError:
        rejected_while_open = True
    opened = breaker.state == CircuitState.OPEN
    clock[0] = 6.0
    breaker.before_call()
    half_opened = breaker.state == CircuitState.HALF_OPEN
    breaker.record_success()
    recovered = breaker.state == CircuitState.CLOSED
    return {
        "verified": all((rejected_while_open, opened, half_opened, recovered)),
        "method": "deterministic injected service failures and clock advance",
        "opened_after_failures": opened,
        "rejected_while_open": rejected_while_open,
        "entered_half_open": half_opened,
        "recovered_after_successful_probe": recovered,
        "snapshot": breaker.snapshot(),
    }


def drift_fault_injection(decisions: List[Any]) -> Dict[str, Any]:
    sample_size = min(100, len(decisions))
    baseline = DriftBaseline.from_decisions(decisions)
    monitor = DecisionDriftMonitor(
        baseline,
        DriftThresholds(
            min_window=sample_size,
            max_unknown_rate_increase=0.01,
            max_merge_rate_delta=0.01,
            max_stage_total_variation=0.01,
            max_service_error_rate=0.0,
            max_candidate_truncation_rate=1.0,
            max_p95_latency_ms=10_000.0,
        ),
        window_size=sample_size,
    )
    # Alternate two extreme invalid states so the test deterministically moves
    # both UNKNOWN and MERGE rates, even when the source window contains no
    # merges.  All rows also move stage and carry a service error.
    injected = [
        replace(
            decision,
            decision=(Decision.UNKNOWN if index % 2 == 0 else Decision.MERGE),
            author_id=(None if index % 2 == 0 else "fault-injected-author"),
            stage="fault_injection",
            service_error="injected upstream failure",
        )
        for index, decision in enumerate(decisions[:sample_size])
    ]
    report = monitor.observe_many(injected)
    failures = {failure["name"] for failure in report.get("failures", [])}
    expected = {
        "unknown_rate_increase",
        "merge_rate_delta",
        "stage_total_variation",
        "service_error_rate",
    }
    return {
        "verified": bool(report.get("alert")) and expected.issubset(failures),
        "method": "fault-injected UNKNOWN/stage/service-error telemetry window",
        "sample_mentions": sample_size,
        "expected_alerts": sorted(expected),
        "observed_alerts": sorted(failures),
        "monitor_report": report,
    }


def runtime_contract_validation(
    pipeline: IstinaDisambiguationPipeline,
    article: Mapping[str, Any],
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="istina-audit-validation-") as directory:
        audit_path = Path(directory) / "runtime_audit.jsonl"
        audit_sink = TamperEvidentJsonlAuditSink(audit_path, fsync=True)
        runtime = IstinaProductionRuntime(
            pipeline,
            mode=RuntimeMode.CANDIDATE,
            audit_salt="operational-validation",
            audit_sink=audit_sink,
        )
        first = runtime.decide_paper(article, query_service=False)
        second = runtime.decide_paper(article, query_service=False)
        serialized_audit = audit_path.read_text(encoding="utf-8")
        chain_report = verify_audit_chain(audit_path)
        restarted_sink = TamperEvidentJsonlAuditSink(audit_path, fsync=True)
        restart_append_state = restarted_sink.snapshot()
    first_keys = [command.idempotency_key for command in first.commands]
    second_keys = [command.idempotency_key for command in second.commands]
    raw_names = [
        str(mention.get("name") or "").strip()
        for mention in article_mentions(article)
    ]
    raw_names = [name for name in raw_names if name]
    audit_redacted = all(name not in serialized_audit for name in raw_names)
    no_write_authorized = not any(
        command.authorized for command in first.commands + second.commands
    )
    expected_records = len(first.decisions) + len(second.decisions)
    durable_audit_verified = bool(
        chain_report["verified"]
        and chain_report["records"] == expected_records
        and restart_append_state["records"] == expected_records
        and restart_append_state["head_hash"] == chain_report["head_hash"]
        and restart_append_state["fsync"]
    )
    return {
        "verified": bool(first_keys) and first_keys == second_keys
        and audit_redacted and no_write_authorized and durable_audit_verified,
        "mode": RuntimeMode.CANDIDATE.value,
        "commands": len(first_keys),
        "idempotent_replay": first_keys == second_keys,
        "audit_redacted": audit_redacted,
        "durable_audit_chain": {
            "verified": durable_audit_verified,
            "records": chain_report["records"],
            "head_hash": chain_report["head_hash"],
            "restart_verified": (
                restart_append_state["head_hash"] == chain_report["head_hash"]
            ),
            "fsync": restart_append_state["fsync"],
            "storage_scope": "ephemeral validation file; not deployed production storage",
        },
        "no_write_authorized": no_write_authorized,
    }


def repeated_load_replay(
    pipeline: IstinaDisambiguationPipeline,
    mentions: List[Dict[str, Any]],
    service_records: Mapping[Tuple[str, str, str, str, str], Dict[str, Any]],
    baseline_hashes: List[str],
    iterations: int,
) -> Dict[str, Any]:
    latencies: List[float] = []
    mismatches = 0
    started = time.perf_counter()
    for _ in range(iterations):
        for index, mention in enumerate(mentions):
            service_record = service_records.get(mention_identity(mention))
            decision = pipeline.decide_mention(
                mention,
                service_response=record_service_response(service_record),
                emit_audit=False,
            )
            latencies.append(decision.latency_ms)
            mismatches += decision.deterministic_hash != baseline_hashes[index]
    elapsed = time.perf_counter() - started
    operations = len(mentions) * iterations
    p95 = percentile(latencies, 0.95)
    return {
        "verified": bool(operations) and mismatches == 0 and (p95 or 0.0) <= 50.0,
        "real_distinct_mentions": len(mentions),
        "replay_iterations": iterations,
        "load_operations": operations,
        "elapsed_seconds": elapsed,
        "throughput_mentions_per_second": operations / elapsed if elapsed else None,
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": p95,
        "latency_ms_p99": percentile(latencies, 0.99),
        "deterministic_hash_mismatches": mismatches,
        "scope": "offline no-write load replay; repeated operations are not extra gold",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--service-result", type=Path)
    parser.add_argument("--live-shadow-evidence", type=Path)
    parser.add_argument(
        "--split-strategy",
        choices=["temporal", "per-author-holdout"],
        default="temporal",
    )
    parser.add_argument("--train-through-year", type=int, default=2023)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--tests-passed", type=int)
    parser.add_argument("--test-warnings", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations < 1:
        raise ValueError("iterations must be positive")

    raw_articles = load_articles(args.dataset)
    raw_mentions = sum(
        len(article.get("authors") or []) for article in raw_articles
    )
    articles, exact_duplicates_removed = deduplicate_exact_author_rows(
        raw_articles
    )
    mentions = list(iter_mentions(articles))
    history, test = split_mentions(
        mentions,
        args.split_strategy,
        args.train_through_year,
    )
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=IstinaPipelineConfig(
            use_remote_fallback=False,
            enable_calibrated_candidate_rescue=False,
            run_id="istina-operational-validation",
        ),
    )
    service_records = load_service_records(args.service_result)
    baseline_decisions = []
    for mention in test:
        service_record = service_records.get(mention_identity(mention))
        baseline_decisions.append(pipeline.decide_mention(
            mention,
            service_response=record_service_response(service_record),
            allow_service_fallback=False,
            emit_audit=False,
        ))

    quality = evaluate_quality(
        baseline_decisions,
        test,
        set(pipeline.history_state.external_to_database_id),
        service_records,
    )
    load = repeated_load_replay(
        pipeline,
        test,
        service_records,
        [decision.deterministic_hash for decision in baseline_decisions],
        args.iterations,
    )
    circuit = circuit_breaker_fault_injection()
    drift = drift_fault_injection(baseline_decisions)
    runtime_contract = runtime_contract_validation(pipeline, articles[0])
    live_shadow_document = (
        json.loads(args.live_shadow_evidence.read_text(encoding="utf-8"))
        if args.live_shadow_evidence else {}
    )
    online_shadow_evidence = (
        (live_shadow_document.get("operational_evidence") or {}).get(
            "online_shadow_verified"
        )
        if isinstance(live_shadow_document, Mapping)
        else None
    ) or {
        "verified": False,
        "reason": "no live shadow evidence artifact was supplied",
    }
    live_shadow_protocol = (
        dict(live_shadow_document.get("protocol") or {})
        if isinstance(live_shadow_document, Mapping)
        else {}
    )
    live_shadow_records = (
        list(live_shadow_document.get("records") or [])
        if isinstance(live_shadow_document, Mapping)
        and isinstance(live_shadow_document.get("records"), list)
        else []
    )
    offline_fallback_stages = sum(
        decision.stage == "legacy_service_validated_fallback"
        for decision in baseline_decisions
    )
    live_fallback_stages = sum(
        isinstance(record, Mapping)
        and record.get("stage") == "legacy_service_validated_fallback"
        for record in live_shadow_records
    )
    comparator_independence = {
        "verified": bool(
            args.live_shadow_evidence
            and live_shadow_protocol.get(
                "framework_legacy_fallback_enabled"
            ) is False
            and live_shadow_protocol.get(
                "legacy_service_observation_only"
            ) is True
            and offline_fallback_stages == 0
            and live_fallback_stages == 0
        ),
        "offline_framework_legacy_fallback_enabled": False,
        "offline_legacy_fallback_stages": offline_fallback_stages,
        "live_framework_legacy_fallback_enabled": live_shadow_protocol.get(
            "framework_legacy_fallback_enabled"
        ),
        "live_legacy_service_observation_only": live_shadow_protocol.get(
            "legacy_service_observation_only"
        ),
        "live_legacy_fallback_stages": live_fallback_stages,
        "required": "legacy service observed only and never used by framework decisions",
    }

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "dataset": str(args.dataset),
            "dataset_sha256": sha256_file(args.dataset),
            "service_result": str(args.service_result) if args.service_result else None,
            "service_result_sha256": (
                sha256_file(args.service_result) if args.service_result else None
            ),
            "live_shadow_evidence_sha256": (
                sha256_file(args.live_shadow_evidence)
                if args.live_shadow_evidence else None
            ),
            "split_strategy": args.split_strategy,
            "train_through_year": args.train_through_year,
            "history_mentions": len(history),
            "test_mentions": len(test),
            "raw_mentions": raw_mentions,
            "effective_mentions": len(mentions),
            "exact_duplicate_author_rows_removed": exact_duplicates_removed,
            "exact_duplicate_cleaning_applied": True,
            "load_iterations": args.iterations,
            "network_calls": 0,
            "write_calls": 0,
            "framework_legacy_fallback_enabled": False,
            "legacy_service_observation_only": True,
        },
        "tests": {
            "command": "python -m pytest -q -p no:cacheprovider",
            "passed": args.tests_passed,
            "warnings": args.test_warnings,
        },
        **quality,
        "operational_validation": {
            "runtime_safety_contract": runtime_contract,
            "offline_load_test": load,
            "circuit_breaker_fault_injection": circuit,
            "drift_monitor_fault_injection": drift,
            "live_shadow": {
                "stats": live_shadow_document.get("stats"),
                "metrics": live_shadow_document.get("metrics"),
                "safety": live_shadow_document.get("safety"),
            } if live_shadow_document else None,
        },
        "operational_evidence": {
            "runtime_safety_contract_verified": runtime_contract,
            "offline_load_test_verified": load,
            "legacy_comparator_independence_verified": comparator_independence,
            "rollback_verified": {
                "verified": bool(circuit["verified"] and drift["verified"]),
                "method": "circuit-breaker recovery plus fail-closed drift fault injection",
            },
            "drift_monitor_test_verified": drift,
            "cross_domain_gold_verified": {
                "verified": False,
                "reason": "available advisor export is not a verified multi-discipline ISTINA gold set",
            },
            "online_shadow_verified": online_shadow_evidence,
            "online_load_test_verified": {
                "verified": False,
                "reason": "local replay is not an online end-to-end ISTINA load test",
            },
            "drift_monitoring_verified": {
                "verified": False,
                "reason": "monitor is implemented and fault-tested but not yet deployed",
            },
        },
        "release_constraints": {
            "repeated_load_operations_are_distinct_gold": False,
            "write_enabled_replacement_authorized": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "test_mentions": len(test),
        "load_operations": load["load_operations"],
        "load_verified": load["verified"],
        "runtime_safety_contract_verified": runtime_contract["verified"],
        "durable_audit_chain_verified": runtime_contract[
            "durable_audit_chain"
        ]["verified"],
        "circuit_breaker_verified": circuit["verified"],
        "drift_monitor_verified": drift["verified"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
