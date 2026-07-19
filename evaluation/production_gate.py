"""Machine-readable production release gate for ISTINA runtime replays."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ReleaseCriteria:
    min_total_mentions: int = 10_000
    min_existing_mentions: int = 1_000
    min_new_mentions: int = 1_000
    min_shadow_mentions: int = 500
    min_merge_precision: float = 0.995
    min_existing_recall: float = 0.95
    min_auto_accuracy: float = 0.98
    max_unknown_rate: float = 0.02
    max_wrong_merge_rate: float = 0.001
    max_unseen_false_link_rate: float = 0.001
    max_local_p95_latency_ms: float = 50.0
    min_shadow_absolute_gain: float = 0.02
    max_shadow_p_value: float = 0.05


def _check(
    name: str,
    observed: Any,
    required: Any,
    passed: bool,
    category: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "passed": bool(passed),
        "observed": observed,
        "required": required,
    }


def _evidence_verified(evidence: Mapping[str, Any], name: str) -> bool:
    """Read legacy booleans or structured operational evidence records."""

    value = evidence.get(name, False)
    if isinstance(value, Mapping):
        return bool(value.get("verified", False))
    return bool(value)


def assess_production_readiness(
    replay: Mapping[str, Any],
    criteria: Optional[ReleaseCriteria] = None,
    evidence: Optional[Mapping[str, bool]] = None,
) -> Dict[str, Any]:
    criteria = criteria or ReleaseCriteria()
    evidence = dict(evidence or {})
    stats = dict(replay.get("stats") or {})
    metrics = dict(replay.get("metrics") or {})
    shadow = dict(replay.get("legacy_shadow") or {})

    total = int(stats.get("total") or 0)
    existing = int(stats.get("existing_gold") or 0)
    new = int(stats.get("new_gold") or 0)
    merge_for_new = int(stats.get("merge_for_new_gold") or 0)
    unseen_false_link_rate = merge_for_new / new if new else None
    shadow_n = int(shadow.get("n") or 0)
    runtime_correct = int(shadow.get("runtime_correct") or 0)
    legacy_correct = int(shadow.get("legacy_correct") or 0)
    shadow_gain = (
        (runtime_correct - legacy_correct) / shadow_n
        if shadow_n else None
    )
    p_value = shadow.get("mcnemar_exact_two_sided_p")

    checks = [
        _check("total_mentions", total, f">={criteria.min_total_mentions}", total >= criteria.min_total_mentions, "data"),
        _check("existing_mentions", existing, f">={criteria.min_existing_mentions}", existing >= criteria.min_existing_mentions, "data"),
        _check("new_mentions", new, f">={criteria.min_new_mentions}", new >= criteria.min_new_mentions, "data"),
        _check("shadow_mentions", shadow_n, f">={criteria.min_shadow_mentions}", shadow_n >= criteria.min_shadow_mentions, "data"),
        _check(
            "merge_precision",
            metrics.get("precision"),
            f">={criteria.min_merge_precision}",
            metrics.get("precision") is not None and metrics["precision"] >= criteria.min_merge_precision,
            "quality",
        ),
        _check(
            "existing_recall",
            metrics.get("existing_recall"),
            f">={criteria.min_existing_recall}",
            metrics.get("existing_recall") is not None and metrics["existing_recall"] >= criteria.min_existing_recall,
            "quality",
        ),
        _check(
            "auto_accuracy",
            metrics.get("auto_accuracy"),
            f">={criteria.min_auto_accuracy}",
            metrics.get("auto_accuracy") is not None and metrics["auto_accuracy"] >= criteria.min_auto_accuracy,
            "quality",
        ),
        _check(
            "unknown_rate",
            metrics.get("unknown_rate"),
            f"<={criteria.max_unknown_rate}",
            metrics.get("unknown_rate") is not None and metrics["unknown_rate"] <= criteria.max_unknown_rate,
            "quality",
        ),
        _check(
            "wrong_merge_rate",
            metrics.get("wrong_merge_rate"),
            f"<={criteria.max_wrong_merge_rate}",
            metrics.get("wrong_merge_rate") is not None and metrics["wrong_merge_rate"] <= criteria.max_wrong_merge_rate,
            "quality",
        ),
        _check(
            "unseen_false_link_rate",
            unseen_false_link_rate,
            f"<={criteria.max_unseen_false_link_rate}",
            unseen_false_link_rate is not None and unseen_false_link_rate <= criteria.max_unseen_false_link_rate,
            "quality",
        ),
        _check(
            "local_p95_latency_ms",
            metrics.get("latency_ms_p95"),
            f"<={criteria.max_local_p95_latency_ms}",
            metrics.get("latency_ms_p95") is not None and metrics["latency_ms_p95"] <= criteria.max_local_p95_latency_ms,
            "performance",
        ),
        _check(
            "shadow_absolute_gain",
            shadow_gain,
            f">={criteria.min_shadow_absolute_gain}",
            shadow_gain is not None and shadow_gain >= criteria.min_shadow_absolute_gain,
            "comparison",
        ),
        _check(
            "shadow_significance",
            p_value,
            f"<={criteria.max_shadow_p_value}",
            p_value is not None and p_value <= criteria.max_shadow_p_value,
            "comparison",
        ),
    ]

    operational_requirements = {
        "runtime_safety_contract_verified": "write authorization, idempotency, redaction, and fail-closed runtime contract",
        "offline_load_test_verified": "deterministic no-write load replay on real ISTINA data",
        "legacy_comparator_independence_verified": (
            "framework decisions do not consume legacy-service outputs used "
            "as the paired comparator"
        ),
        "cross_domain_gold_verified": "validated gold from multiple ISTINA disciplines",
        "online_shadow_verified": "live shadow run without writes",
        "online_load_test_verified": "online end-to-end load and latency test",
        "rollback_verified": "tested rollback/circuit-breaker procedure",
        "drift_monitor_test_verified": "fault-injected drift monitor alert verification",
        "drift_monitoring_verified": "deployed data-quality and decision-drift monitoring",
        "paired_shadow_analysis_verified": (
            "pre-registered, adequately powered, paper-cluster-aware paired "
            "comparison against the legacy service"
        ),
    }
    for name, requirement in operational_requirements.items():
        verified = _evidence_verified(evidence, name)
        checks.append(_check(
            name,
            verified,
            requirement,
            verified,
            "operations",
        ))

    failures = [check for check in checks if not check["passed"]]
    return {
        "release_ready": not failures,
        "criteria": asdict(criteria),
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-result", type=Path, required=True)
    parser.add_argument("--criteria", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    replay = json.loads(args.replay_result.read_text(encoding="utf-8"))
    criteria = ReleaseCriteria(**(
        json.loads(args.criteria.read_text(encoding="utf-8"))
        if args.criteria else {}
    ))
    evidence_document = (
        json.loads(args.evidence.read_text(encoding="utf-8"))
        if args.evidence else {}
    )
    evidence = (
        evidence_document.get("operational_evidence")
        if isinstance(evidence_document, Mapping)
        and isinstance(evidence_document.get("operational_evidence"), Mapping)
        else evidence_document
    )
    result = assess_production_readiness(replay, criteria, evidence)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
