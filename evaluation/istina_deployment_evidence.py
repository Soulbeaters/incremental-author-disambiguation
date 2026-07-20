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
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.istina_audit_retention import (  # noqa: E402
    AUDIT_CHAIN_MANIFEST_ALGORITHM,
    AUDIT_HEAD_HASH_SCOPE,
    AUDIT_RETENTION_METHOD,
    CHAIN_ENTRY_FIELDS,
    audit_chain_manifest_sha256,
)
from evaluation.istina_online_load_plan import (  # noqa: E402
    INSTITUTIONAL_LOAD_SCOPE,
    assess_online_load_plan,
)


REQUIRED_ATTACHMENT_ROLES = {
    "shadow_telemetry",
    "online_load",
    "online_load_plan",
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


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _same_number(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    return bool(
        left_number is not None
        and right_number is not None
        and abs(left_number - right_number) <= tolerance
    )


def assess_deployment_evidence(
    manifest: Mapping[str, Any] | None,
    observed_attachments: Sequence[Mapping[str, Any]],
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

    declared_attachment_rows = [
        (
            str(item.get("role") or ""),
            str(item.get("name") or ""),
            str(item.get("sha256") or "").lower(),
        )
        for item in document.get("attachments") or []
        if isinstance(item, Mapping)
    ]
    declared_attachments = set(declared_attachment_rows)
    observed_rows = [
        (
            str(item.get("name") or ""),
            str(item.get("sha256") or "").lower(),
        )
        for item in observed_attachments
        if isinstance(item, Mapping)
    ]
    observed = set(observed_rows)
    declared_files = {(name, digest) for _role, name, digest in declared_attachments}
    declared_roles = {role for role, _name, _digest in declared_attachments}
    declared_names = {name for _role, name, _digest in declared_attachments}
    attachment_hashes_valid = bool(declared_attachments) and all(
        role and name and re.fullmatch(r"[0-9a-f]{64}", digest)
        for role, name, digest in declared_attachments
    )
    attachment_cardinality_valid = bool(
        len(declared_attachment_rows) == len(REQUIRED_ATTACHMENT_ROLES)
        and len(declared_attachments) == len(REQUIRED_ATTACHMENT_ROLES)
        and len(declared_names) == len(REQUIRED_ATTACHMENT_ROLES)
        and len(observed_rows) == len(REQUIRED_ATTACHMENT_ROLES)
        and len(observed) == len(REQUIRED_ATTACHMENT_ROLES)
    )
    roles_by_name = {
        name: role for role, name, _digest in declared_attachment_rows
    }
    declared_by_role = {
        role: {"name": name, "sha256": digest}
        for role, name, digest in declared_attachment_rows
    }
    documents_by_role: Dict[str, Dict[str, Any]] = {}
    document_errors: Dict[str, str] = {}
    for item in observed_attachments:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "")
        role = roles_by_name.get(name)
        if not role:
            continue
        attachment_document = item.get("document")
        if isinstance(attachment_document, Mapping):
            documents_by_role[role] = dict(attachment_document)
        else:
            document_errors[role] = str(
                item.get("document_error") or "JSON object was not loaded"
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

    shadow_document = documents_by_role.get("shadow_telemetry", {})
    shadow_protocol = _mapping(shadow_document.get("protocol"))
    shadow_stats = _mapping(shadow_document.get("stats"))
    shadow_metrics = _mapping(shadow_document.get("metrics"))
    shadow_safety = _mapping(shadow_document.get("safety"))
    shadow_release = _mapping(
        _mapping(shadow_document.get("operational_evidence")).get(
            "online_shadow_verified"
        )
    )
    shadow_audit = _mapping(shadow_safety.get("durable_audit_chain"))

    load_document = documents_by_role.get("online_load", {})
    load_protocol = _mapping(load_document.get("protocol"))
    load_stats = _mapping(load_document.get("stats"))
    load_metrics = _mapping(load_document.get("metrics"))
    load_safety = _mapping(load_document.get("safety"))
    load_plan_document = documents_by_role.get("online_load_plan", {})
    load_plan_attachment = declared_by_role.get("online_load_plan", {})
    load_execution_started_at = _timestamp(
        load_protocol.get("execution_started_at")
    )
    load_plan_validation = assess_online_load_plan(
        load_plan_document,
        expected_dataset_sha256=expected_dataset_sha256,
        expected_code_revision=expected_code_revision,
        expected_service_url_sha256=str(
            load_protocol.get("service_url_sha256") or ""
        ),
        expected_man_id_sha256=str(load_protocol.get("man_id_sha256") or ""),
        expected_requests=load_protocol.get("requests"),
        expected_concurrency=load_protocol.get("concurrency"),
        expected_max_rps=load_protocol.get("max_rps"),
        expected_service_timeout_seconds=load_protocol.get(
            "service_timeout_seconds"
        ),
        expected_change_reference=str(
            load_protocol.get("approved_change_reference") or ""
        ),
        validation_time=load_execution_started_at,
        require_active_window=True,
    )

    drift_document = documents_by_role.get("drift_monitor", {})
    drift_window = _mapping(drift_document.get("window"))
    drift_proof = _mapping(drift_document.get("verification"))

    audit_document = documents_by_role.get("audit_verification", {})
    audit_proof = _mapping(audit_document.get("verification"))
    audit_records = _integer(audit_proof.get("records"))
    audit_chain_count = _integer(audit_proof.get("chain_count"))
    audit_telemetry_count = _integer(audit_proof.get("telemetry_count"))
    audit_chain_entries = [
        dict(item)
        for item in audit_proof.get("chain_entries") or []
        if isinstance(item, Mapping)
    ]
    audit_entry_records = [
        _integer(item.get("records")) for item in audit_chain_entries
    ]
    audit_entries_valid = bool(audit_chain_entries) and all(
        set(item) == CHAIN_ENTRY_FIELDS
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(item.get("chain_sha256") or "").lower(),
        )
        is not None
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(item.get("telemetry_sha256") or "").lower(),
        )
        is not None
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(item.get("head_hash") or "").lower(),
        )
        is not None
        and _integer(item.get("records")) is not None
        and int(item["records"]) > 0
        for item in audit_chain_entries
    )
    audit_entries_unique = bool(audit_chain_entries) and all(
        len({str(item.get(field) or "").lower() for item in audit_chain_entries})
        == len(audit_chain_entries)
        for field in ("chain_sha256", "telemetry_sha256", "head_hash")
    )
    audit_entries_ordered = audit_chain_entries == sorted(
        audit_chain_entries,
        key=lambda item: str(item.get("chain_sha256") or ""),
    )
    audit_manifest_sha256 = str(
        audit_proof.get("chain_manifest_sha256") or ""
    ).lower()
    recomputed_audit_manifest_sha256 = (
        audit_chain_manifest_sha256(audit_chain_entries)
        if audit_entries_valid
        else None
    )

    shadow_attachment_identity = [
        shadow_document.get("schema_version"),
        shadow_protocol.get("dataset_sha256"),
        shadow_protocol.get("code_revision"),
        shadow_protocol.get("mode"),
    ]
    expected_shadow_attachment_identity = [
        1,
        expected_dataset_sha256,
        expected_code_revision,
        "shadow",
    ]
    shadow_attachment_counts = [
        shadow_stats.get("attempted_mentions"),
        shadow_stats.get("service_errors"),
        shadow_protocol.get("write_calls"),
        shadow_stats.get("authorized_commands"),
    ]
    expected_shadow_attachment_counts = [shadow_mentions, shadow_errors, 0, 0]
    load_attachment_identity = [
        load_document.get("schema_version"),
        load_protocol.get("dataset_sha256"),
        load_protocol.get("code_revision"),
        load_protocol.get("mode"),
    ]
    expected_load_attachment_identity = [
        1,
        expected_dataset_sha256,
        expected_code_revision,
        "read_only_candidate_lookup",
    ]
    load_attachment_counts = [
        load_stats.get("requests"),
        load_stats.get("completed"),
        load_stats.get("errors"),
        load_stats.get("write_calls"),
        load_stats.get("requests_outside_approved_window"),
    ]
    expected_load_attachment_counts = [
        load_requests,
        load_requests,
        load_errors,
        0,
        0,
    ]
    drift_attachment_identity = [
        drift_document.get("schema_version"),
        drift_document.get("source_system"),
        drift_document.get("dataset_sha256"),
        drift_document.get("code_revision"),
    ]
    expected_deployment_attachment_identity = [
        1,
        "istina",
        expected_dataset_sha256,
        expected_code_revision,
    ]
    drift_attachment_window = [drift_window.get("start"), drift_window.get("end")]
    expected_attachment_window = [window.get("start"), window.get("end")]
    drift_attachment_values = [
        drift_proof.get("active"),
        drift_proof.get("observation_hours"),
        drift_proof.get("paging_route_verified"),
        drift_proof.get("injected_alert_received"),
    ]
    expected_drift_attachment_values = [
        drift.get("active"),
        drift.get("observation_hours"),
        drift.get("paging_route_verified"),
        drift.get("injected_alert_received"),
    ]
    audit_attachment_identity = [
        audit_document.get("schema_version"),
        audit_document.get("source_system"),
        audit_document.get("dataset_sha256"),
        audit_document.get("code_revision"),
    ]
    audit_attachment_values = [
        audit_proof.get("durable"),
        audit_proof.get("chain_verified"),
        audit_proof.get("retention_days"),
    ]
    expected_audit_attachment_values = [
        audit.get("durable"),
        audit.get("chain_verified"),
        audit.get("retention_days"),
    ]

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
        _check("attachment_cardinality", {"declared": len(declared_attachment_rows), "observed": len(observed_rows)}, {"declared": len(REQUIRED_ATTACHMENT_ROLES), "observed": len(REQUIRED_ATTACHMENT_ROLES)}, attachment_cardinality_valid, "attachments"),
        _check("attachment_hash_format", attachment_hashes_valid, True, attachment_hashes_valid, "attachments"),
        _check("attachment_hashes", sorted(declared_files), sorted(observed), declared_files == observed, "attachments"),
        _check("attachment_documents", sorted(documents_by_role), sorted(REQUIRED_ATTACHMENT_ROLES), set(documents_by_role) == REQUIRED_ATTACHMENT_ROLES and not document_errors, "attachments"),
        _check(
            "shadow_attachment_identity",
            shadow_attachment_identity,
            expected_shadow_attachment_identity,
            shadow_attachment_identity == expected_shadow_attachment_identity,
            "shadow_attachment",
        ),
        _check(
            "shadow_attachment_counts",
            shadow_attachment_counts,
            expected_shadow_attachment_counts,
            shadow_attachment_counts == expected_shadow_attachment_counts,
            "shadow_attachment",
        ),
        _check(
            "shadow_attachment_error_rate",
            shadow_metrics.get("service_error_rate"),
            shadow_error_rate,
            _same_number(
                shadow_metrics.get("service_error_rate"), shadow_error_rate
            ),
            "shadow_attachment",
        ),
        _check(
            "shadow_attachment_safety",
            [
                shadow_release.get("verified"),
                shadow_safety.get("no_write_authorized"),
                shadow_audit.get("verified"),
                shadow_audit.get("retained"),
            ],
            [True, True, True, True],
            [
                shadow_release.get("verified"),
                shadow_safety.get("no_write_authorized"),
                shadow_audit.get("verified"),
                shadow_audit.get("retained"),
            ] == [True, True, True, True],
            "shadow_attachment",
        ),
        _check(
            "load_attachment_identity",
            load_attachment_identity,
            expected_load_attachment_identity,
            load_attachment_identity == expected_load_attachment_identity,
            "load_attachment",
        ),
        _check(
            "load_attachment_counts",
            load_attachment_counts,
            expected_load_attachment_counts,
            load_attachment_counts == expected_load_attachment_counts,
            "load_attachment",
        ),
        _check(
            "load_attachment_metrics",
            [
                load_metrics.get("error_rate"),
                load_metrics.get("latency_ms_p95"),
            ],
            [load_error_rate, load_p95],
            _same_number(load_metrics.get("error_rate"), load_error_rate)
            and _same_number(load_metrics.get("latency_ms_p95"), load_p95),
            "load_attachment",
        ),
        _check(
            "load_attachment_safety",
            [
                load_safety.get("verified"),
                load_safety.get("write_client_present"),
                load_safety.get("write_calls"),
                load_safety.get("threshold_passed"),
                load_safety.get("institutional_approval"),
                load_safety.get("load_plan_verified"),
                load_safety.get("repository_head_verified"),
                load_safety.get("repository_source_tree_clean_verified"),
            ],
            [True, False, 0, True, True, True, True, True],
            [
                load_safety.get("verified"),
                load_safety.get("write_client_present"),
                load_safety.get("write_calls"),
                load_safety.get("threshold_passed"),
                load_safety.get("institutional_approval"),
                load_safety.get("load_plan_verified"),
                load_safety.get("repository_head_verified"),
                load_safety.get("repository_source_tree_clean_verified"),
            ] == [True, False, 0, True, True, True, True, True],
            "load_attachment",
        ),
        _check(
            "load_attachment_plan_binding",
            {
                "plan_name": load_protocol.get("online_load_plan_name"),
                "plan_sha256": str(
                    load_protocol.get("online_load_plan_sha256") or ""
                ).lower(),
                "approval_scope": load_protocol.get("approval_scope"),
                "execution_started_at": load_protocol.get(
                    "execution_started_at"
                ),
            },
            {
                "plan_name": load_plan_attachment.get("name"),
                "plan_sha256": load_plan_attachment.get("sha256"),
                "approval_scope": INSTITUTIONAL_LOAD_SCOPE,
                "execution_started_at": "timezone-aware ISO-8601",
            },
            bool(load_plan_attachment)
            and load_protocol.get("online_load_plan_name")
            == load_plan_attachment.get("name")
            and str(load_protocol.get("online_load_plan_sha256") or "").lower()
            == load_plan_attachment.get("sha256")
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(load_plan_attachment.get("sha256") or ""),
            )
            is not None
            and load_protocol.get("approval_scope") == INSTITUTIONAL_LOAD_SCOPE
            and load_execution_started_at is not None,
            "load_attachment",
        ),
        _check(
            "online_load_plan_validation",
            {
                "verified": load_plan_validation["verified"],
                "summary": load_plan_validation["summary"],
            },
            "all immutable plan bindings and active approved window pass",
            load_plan_validation["verified"],
            "load_attachment",
        ),
        _check(
            "drift_attachment_identity",
            drift_attachment_identity,
            expected_deployment_attachment_identity,
            drift_attachment_identity == expected_deployment_attachment_identity,
            "monitoring_attachment",
        ),
        _check(
            "drift_attachment_window",
            drift_attachment_window,
            expected_attachment_window,
            drift_attachment_window == expected_attachment_window,
            "monitoring_attachment",
        ),
        _check(
            "drift_attachment_values",
            drift_attachment_values,
            expected_drift_attachment_values,
            drift_attachment_values == expected_drift_attachment_values,
            "monitoring_attachment",
        ),
        _check(
            "drift_attachment_references",
            {
                "monitor_config_sha256": drift_proof.get("monitor_config_sha256"),
                "telemetry_source_reference": drift_proof.get("telemetry_source_reference"),
                "paging_test_reference": drift_proof.get("paging_test_reference"),
            },
            "64-hex monitor hash and non-empty telemetry/paging references",
            re.fullmatch(
                r"[0-9a-f]{64}",
                str(drift_proof.get("monitor_config_sha256") or "").lower(),
            ) is not None
            and bool(str(drift_proof.get("telemetry_source_reference") or "").strip())
            and bool(str(drift_proof.get("paging_test_reference") or "").strip()),
            "monitoring_attachment",
        ),
        _check("drift_attachment_timestamp", drift_document.get("generated_at"), "timezone-aware ISO-8601", _timestamp(drift_document.get("generated_at")) is not None, "monitoring_attachment"),
        _check(
            "audit_attachment_identity",
            audit_attachment_identity,
            expected_deployment_attachment_identity,
            audit_attachment_identity == expected_deployment_attachment_identity,
            "audit_attachment",
        ),
        _check(
            "audit_attachment_values",
            audit_attachment_values,
            expected_audit_attachment_values,
            audit_attachment_values == expected_audit_attachment_values,
            "audit_attachment",
        ),
        _check(
            "audit_attachment_machine_verification",
            [
                audit_proof.get("verification_method"),
                audit_proof.get("chain_manifest_algorithm"),
                audit_proof.get("head_hash_scope"),
                audit_proof.get("telemetry_binding_verified"),
            ],
            [
                AUDIT_RETENTION_METHOD,
                AUDIT_CHAIN_MANIFEST_ALGORITHM,
                AUDIT_HEAD_HASH_SCOPE,
                True,
            ],
            [
                audit_proof.get("verification_method"),
                audit_proof.get("chain_manifest_algorithm"),
                audit_proof.get("head_hash_scope"),
                audit_proof.get("telemetry_binding_verified"),
            ]
            == [
                AUDIT_RETENTION_METHOD,
                AUDIT_CHAIN_MANIFEST_ALGORITHM,
                AUDIT_HEAD_HASH_SCOPE,
                True,
            ],
            "audit_attachment",
        ),
        _check(
            "audit_attachment_chain_cardinality",
            {
                "chain_count": audit_chain_count,
                "telemetry_count": audit_telemetry_count,
                "entries": len(audit_chain_entries),
            },
            "equal positive counts",
            audit_chain_count is not None
            and audit_chain_count > 0
            and audit_chain_count
            == audit_telemetry_count
            == len(audit_chain_entries),
            "audit_attachment",
        ),
        _check(
            "audit_attachment_chain_entries",
            {
                "schema_valid": audit_entries_valid,
                "unique": audit_entries_unique,
                "deterministically_ordered": audit_entries_ordered,
            },
            {
                "schema_valid": True,
                "unique": True,
                "deterministically_ordered": True,
            },
            audit_entries_valid
            and audit_entries_unique
            and audit_entries_ordered,
            "audit_attachment",
        ),
        _check(
            "audit_attachment_chain_manifest",
            {
                "declared": audit_manifest_sha256,
                "recomputed": recomputed_audit_manifest_sha256,
                "head_hash": str(audit_proof.get("head_hash") or "").lower(),
            },
            "three identical 64-hex aggregate roots",
            re.fullmatch(r"[0-9a-f]{64}", audit_manifest_sha256) is not None
            and audit_manifest_sha256
            == recomputed_audit_manifest_sha256
            == str(audit_proof.get("head_hash") or "").lower(),
            "audit_attachment",
        ),
        _check(
            "audit_attachment_record_total",
            {
                "declared": audit_records,
                "entry_sum": (
                    sum(int(value) for value in audit_entry_records)
                    if audit_entry_records
                    and all(value is not None for value in audit_entry_records)
                    else None
                ),
            },
            "positive equal totals",
            audit_records is not None
            and audit_records > 0
            and audit_entry_records
            and all(value is not None for value in audit_entry_records)
            and audit_records
            == sum(int(value) for value in audit_entry_records),
            "audit_attachment",
        ),
        _check(
            "audit_attachment_privacy",
            audit_proof.get("record_level_content_included"),
            False,
            audit_proof.get("record_level_content_included") is False,
            "audit_attachment",
        ),
        _check(
            "audit_attachment_references",
            {
                "records": audit_proof.get("records"),
                "head_hash": audit_proof.get("head_hash"),
                "storage_reference": audit_proof.get("storage_reference"),
                "retention_policy_reference": audit_proof.get("retention_policy_reference"),
            },
            "positive records, 64-hex head hash, storage and retention references",
            audit_records is not None
            and audit_records > 0
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(audit_proof.get("head_hash") or "").lower(),
            ) is not None
            and bool(str(audit_proof.get("storage_reference") or "").strip())
            and bool(str(audit_proof.get("retention_policy_reference") or "").strip()),
            "audit_attachment",
        ),
        _check("audit_attachment_timestamp", audit_document.get("generated_at"), "timezone-aware ISO-8601", _timestamp(audit_document.get("generated_at")) is not None, "audit_attachment"),
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
        "observed_attachments": [
            {
                "name": str(item.get("name") or ""),
                "sha256": str(item.get("sha256") or "").lower(),
                "document_loaded": isinstance(item.get("document"), Mapping),
                "document_error": item.get("document_error"),
            }
            for item in observed_attachments
            if isinstance(item, Mapping)
        ],
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
        "operational_evidence": {
            "online_shadow_verified": {
                "verified": category_verified({"identity", "binding", "shadow", "attachments", "shadow_attachment", "approval"}),
                "mentions": shadow_mentions,
                "write_calls": shadow_writes,
                "service_error_rate": shadow_error_rate,
                "observation_hours": observation_hours,
            },
            "online_load_test_verified": {
                "verified": category_verified({"identity", "binding", "load", "attachments", "load_attachment", "approval"}),
                "requests": load_requests,
                "error_rate": load_error_rate,
                "p95_latency_ms": load_p95,
                "online_load_plan_sha256": load_plan_attachment.get("sha256"),
                "plan_validation": {
                    "verified": load_plan_validation["verified"],
                    "summary": load_plan_validation["summary"],
                },
            },
            "drift_monitoring_verified": {
                "verified": category_verified({"identity", "binding", "monitoring", "attachments", "monitoring_attachment", "approval"}),
                "observation_hours": drift_hours,
                "paging_route_verified": drift.get("paging_route_verified"),
                "injected_alert_received": drift.get("injected_alert_received"),
            },
            "durable_audit_retention_verified": {
                "verified": category_verified({"identity", "binding", "audit", "attachments", "audit_attachment", "approval"}),
                "retention_days": retention_days,
                "chain_verified": audit.get("chain_verified"),
                "verification_method": audit_proof.get("verification_method"),
                "chain_count": audit_chain_count,
                "records": audit_records,
                "chain_manifest_sha256": audit_manifest_sha256,
            },
        },
    }


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected a JSON object in {path}")
    return dict(document)


def _load_attachment(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "name": path.name,
        "sha256": sha256_file(path),
    }
    try:
        result["document"] = _load(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result["document_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--attachment", type=Path, nargs="+", required=True)
    parser.add_argument("--expected-dataset", type=Path, required=True)
    parser.add_argument("--expected-code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    observed_attachments = [_load_attachment(path) for path in args.attachment]
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
