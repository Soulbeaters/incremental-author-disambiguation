"""Validate institutional ISTINA deployment evidence for release gates.

The manifest is intentionally fail-closed.  It is not enough to assert a
``verified`` boolean: exact attachment hashes, a frozen dataset and code
revision, observation windows, numeric SLOs, durable audit retention, paging,
and independent approval must all pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


REQUIRED_ATTACHMENT_ROLES = {
    "shadow_telemetry",
    "online_load",
    "drift_monitor",
    "audit_verification",
}


@dataclass(frozen=True)
class DeploymentCriteria:
    min_observation_hours: float = 24.0
    min_shadow_mentions: int = 500
    max_shadow_write_calls: int = 0
    max_shadow_service_error_rate: float = 0.01
    min_online_load_requests: int = 1_000
    max_online_load_error_rate: float = 0.01
    max_online_load_p95_latency_ms: float = 20_000.0
    min_drift_monitor_hours: float = 24.0
    min_audit_retention_days: int = 90


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "observed": observed,
        "required": required,
        "passed": bool(passed),
    }


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _rate(numerator: int | None, denominator: int | None) -> float | None:
    if (
        numerator is None
        or denominator is None
        or numerator < 0
        or denominator <= 0
    ):
        return None
    return numerator / denominator


def assess_deployment_evidence(
    manifest: Mapping[str, Any] | None,
    observed_attachments: Sequence[Mapping[str, str]],
    *,
    expected_dataset_sha256: str,
    expected_code_revision: str,
    criteria: DeploymentCriteria | None = None,
) -> Dict[str, Any]:
    criteria = criteria or DeploymentCriteria()
    document = dict(manifest or {})
    window = dict(document.get("window") or {})
    shadow = dict(document.get("shadow") or {})
    online_load = dict(document.get("online_load") or {})
    drift = dict(document.get("drift_monitoring") or {})
    audit = dict(document.get("audit") or {})
    approval = dict(document.get("approval") or {})

    start = _timestamp(window.get("start"))
    end = _timestamp(window.get("end"))
    observation_hours = (
        (end - start).total_seconds() / 3600.0
        if start is not None and end is not None and end > start
        else None
    )
    shadow_mentions = _integer(shadow.get("mentions"))
    shadow_errors = _integer(shadow.get("service_errors"))
    shadow_writes = _integer(shadow.get("write_calls"))
    shadow_error_rate = _rate(shadow_errors, shadow_mentions)
    load_requests = _integer(online_load.get("requests"))
    load_errors = _integer(online_load.get("errors"))
    load_error_rate = _rate(load_errors, load_requests)
    load_p95 = _number(online_load.get("p95_latency_ms"))
    drift_hours = _number(drift.get("observation_hours"))
    retention_days = _integer(audit.get("retention_days"))

    declared_attachments = {
        (
            str(item.get("role") or ""),
            str(item.get("name") or ""),
            str(item.get("sha256") or "").lower(),
        )
        for item in document.get("attachments") or []
        if isinstance(item, Mapping)
    }
    observed = {
        (
            str(item.get("name") or ""),
            str(item.get("sha256") or "").lower(),
        )
        for item in observed_attachments
        if isinstance(item, Mapping)
    }
    declared_files = {(name, digest) for _role, name, digest in declared_attachments}
    declared_roles = {role for role, _name, _digest in declared_attachments}
    attachment_hashes_valid = bool(declared_attachments) and all(
        role and name and re.fullmatch(r"[0-9a-f]{64}", digest)
        for role, name, digest in declared_attachments
    )

    expected_dataset_sha256 = str(expected_dataset_sha256 or "").lower()
    expected_code_revision = str(expected_code_revision or "").lower()
    manifest_dataset_sha256 = str(document.get("dataset_sha256") or "").lower()
    manifest_code_revision = str(document.get("code_revision") or "").lower()
    approval_time = _timestamp(approval.get("approved_at"))
    operations_reference = str(approval.get("operations_reference") or "").strip()
    review_reference = str(
        approval.get("independent_review_reference") or ""
    ).strip()

    checks = [
        _check("manifest_present", bool(document), True, bool(document), "identity"),
        _check("schema_version", document.get("schema_version"), 1, document.get("schema_version") == 1, "identity"),
        _check("source_system", document.get("source_system"), "istina", str(document.get("source_system") or "").casefold() == "istina", "identity"),
        _check("environment", document.get("environment"), "production", str(document.get("environment") or "").casefold() == "production", "identity"),
        _check("dataset_sha256", manifest_dataset_sha256, expected_dataset_sha256, bool(expected_dataset_sha256) and re.fullmatch(r"[0-9a-f]{64}", expected_dataset_sha256) is not None and manifest_dataset_sha256 == expected_dataset_sha256, "binding"),
        _check("code_revision", manifest_code_revision, expected_code_revision, bool(expected_code_revision) and re.fullmatch(r"[0-9a-f]{40}", expected_code_revision) is not None and manifest_code_revision == expected_code_revision, "binding"),
        _check("observation_window", observation_hours, f">={criteria.min_observation_hours} hours", observation_hours is not None and observation_hours >= criteria.min_observation_hours, "shadow"),
        _check("shadow_mentions", shadow_mentions, f">={criteria.min_shadow_mentions}", shadow_mentions is not None and shadow_mentions >= criteria.min_shadow_mentions, "shadow"),
        _check("shadow_write_calls", shadow_writes, criteria.max_shadow_write_calls, shadow_writes is not None and 0 <= shadow_writes <= criteria.max_shadow_write_calls, "shadow"),
        _check("shadow_service_error_rate", shadow_error_rate, f"<={criteria.max_shadow_service_error_rate}", shadow_error_rate is not None and shadow_error_rate <= criteria.max_shadow_service_error_rate, "shadow"),
        _check("online_load_requests", load_requests, f">={criteria.min_online_load_requests}", load_requests is not None and load_requests >= criteria.min_online_load_requests, "load"),
        _check("online_load_error_rate", load_error_rate, f"<={criteria.max_online_load_error_rate}", load_error_rate is not None and load_error_rate <= criteria.max_online_load_error_rate, "load"),
        _check("online_load_p95_latency_ms", load_p95, f"<={criteria.max_online_load_p95_latency_ms}", load_p95 is not None and 0.0 <= load_p95 <= criteria.max_online_load_p95_latency_ms, "load"),
        _check("drift_monitor_active", drift.get("active"), True, drift.get("active") is True, "monitoring"),
        _check("drift_monitor_hours", drift_hours, f">={criteria.min_drift_monitor_hours}", drift_hours is not None and drift_hours >= criteria.min_drift_monitor_hours, "monitoring"),
        _check("drift_window_consistent", drift_hours, "no longer than observation window", drift_hours is not None and observation_hours is not None and drift_hours <= observation_hours, "monitoring"),
        _check("paging_route_verified", drift.get("paging_route_verified"), True, drift.get("paging_route_verified") is True, "monitoring"),
        _check("injected_alert_received", drift.get("injected_alert_received"), True, drift.get("injected_alert_received") is True, "monitoring"),
        _check("durable_audit", audit.get("durable"), True, audit.get("durable") is True, "audit"),
        _check("audit_chain_verified", audit.get("chain_verified"), True, audit.get("chain_verified") is True, "audit"),
        _check("audit_retention_days", retention_days, f">={criteria.min_audit_retention_days}", retention_days is not None and retention_days >= criteria.min_audit_retention_days, "audit"),
        _check("attachment_roles", sorted(declared_roles), sorted(REQUIRED_ATTACHMENT_ROLES), declared_roles == REQUIRED_ATTACHMENT_ROLES, "attachments"),
        _check("attachment_hash_format", attachment_hashes_valid, True, attachment_hashes_valid, "attachments"),
        _check("attachment_hashes", sorted(declared_files), sorted(observed), declared_files == observed, "attachments"),
        _check("operations_approval", bool(operations_reference), "non-empty reference", bool(operations_reference), "approval"),
        _check("independent_review", review_reference, "distinct non-empty reference", bool(review_reference) and review_reference != operations_reference, "approval"),
        _check("approval_timestamp", approval.get("approved_at"), "timezone-aware ISO-8601", approval_time is not None, "approval"),
        _check("approval_after_observation", approval.get("approved_at"), "at or after observation end", approval_time is not None and end is not None and approval_time >= end, "approval"),
    ]
    failures = [check for check in checks if not check["passed"]]

    def category_verified(categories: set[str]) -> bool:
        return all(
            check["passed"] for check in checks if check["category"] in categories
        )

    return {
        "schema_version": 1,
        "verified": not failures,
        "criteria": asdict(criteria),
        "expected_dataset_sha256": expected_dataset_sha256,
        "expected_code_revision": expected_code_revision,
        "manifest": document,
        "observed_attachments": [dict(item) for item in observed_attachments],
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
        "operational_evidence": {
            "online_shadow_verified": {
                "verified": category_verified({"identity", "binding", "shadow", "attachments", "approval"}),
                "mentions": shadow_mentions,
                "write_calls": shadow_writes,
                "service_error_rate": shadow_error_rate,
                "observation_hours": observation_hours,
            },
            "online_load_test_verified": {
                "verified": category_verified({"identity", "binding", "load", "attachments", "approval"}),
                "requests": load_requests,
                "error_rate": load_error_rate,
                "p95_latency_ms": load_p95,
            },
            "drift_monitoring_verified": {
                "verified": category_verified({"identity", "binding", "monitoring", "attachments", "approval"}),
                "observation_hours": drift_hours,
                "paging_route_verified": drift.get("paging_route_verified"),
                "injected_alert_received": drift.get("injected_alert_received"),
            },
            "durable_audit_retention_verified": {
                "verified": category_verified({"identity", "binding", "audit", "attachments", "approval"}),
                "retention_days": retention_days,
                "chain_verified": audit.get("chain_verified"),
            },
        },
    }


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected a JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--attachment", type=Path, nargs="+", required=True)
    parser.add_argument("--expected-dataset", type=Path, required=True)
    parser.add_argument("--expected-code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    observed_attachments = [
        {"name": path.name, "sha256": sha256_file(path)}
        for path in args.attachment
    ]
    result = assess_deployment_evidence(
        _load(args.manifest),
        observed_attachments,
        expected_dataset_sha256=sha256_file(args.expected_dataset),
        expected_code_revision=args.expected_code_revision,
    )
    result["inputs"] = {
        "manifest": {
            "name": args.manifest.name,
            "sha256": sha256_file(args.manifest),
        },
        "expected_dataset": {
            "name": args.expected_dataset.name,
            "sha256": sha256_file(args.expected_dataset),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "verified": result["verified"],
        "passed": result["summary"]["passed"],
        "total": result["summary"]["total"],
        "failed_checks": [item["name"] for item in result["failures"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = [
    "DeploymentCriteria",
    "REQUIRED_ATTACHMENT_ROLES",
    "assess_deployment_evidence",
]
