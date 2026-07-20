"""Validate that a gold artifact is genuinely eligible ISTINA identity data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Sequence


def _check(
    name: str,
    observed: Any,
    required: Any,
    passed: bool,
) -> Dict[str, Any]:
    return {
        "name": name,
        "observed": observed,
        "required": required,
        "passed": bool(passed),
    }


def _has_timezone_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def assess_istina_provenance(
    manifest: Mapping[str, Any] | None,
    dataset_inputs: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Return fail-closed provenance checks for production-gold eligibility.

    Crossref/ORCID and other public corpora are valuable external validation,
    but they must never satisfy a gate that specifically requires adjudicated
    ISTINA person identities.
    """

    document = dict(manifest or {})
    declared_datasets = {
        (str(item.get("name") or ""), str(item.get("sha256") or "").lower())
        for item in document.get("datasets") or []
        if isinstance(item, Mapping)
    }
    observed_datasets = {
        (str(item.get("name") or ""), str(item.get("sha256") or "").lower())
        for item in dataset_inputs
    }
    approval = dict(document.get("approval") or {})
    checks = [
        _check(
            "manifest_present",
            bool(document),
            True,
            bool(document),
        ),
        _check(
            "schema_version",
            document.get("schema_version"),
            1,
            document.get("schema_version") == 1,
        ),
        _check(
            "source_system",
            document.get("source_system"),
            "istina",
            str(document.get("source_system") or "").casefold() == "istina",
        ),
        _check(
            "source_record_type",
            document.get("source_record_type"),
            "publication_author_export",
            document.get("source_record_type") == "publication_author_export",
        ),
        _check(
            "identity_namespace",
            document.get("identity_namespace"),
            "istina_author_id",
            document.get("identity_namespace") == "istina_author_id",
        ),
        _check(
            "label_semantics",
            document.get("label_semantics"),
            "adjudicated_person_identity",
            document.get("label_semantics") == "adjudicated_person_identity",
        ),
        _check(
            "exported_at",
            document.get("exported_at"),
            "timezone-aware ISO-8601 timestamp",
            _has_timezone_iso8601(document.get("exported_at")),
        ),
        _check(
            "extraction_method",
            bool(str(document.get("extraction_method") or "").strip()),
            "non-empty documented method",
            bool(str(document.get("extraction_method") or "").strip()),
        ),
        _check(
            "dataset_hashes",
            sorted(declared_datasets),
            sorted(observed_datasets),
            bool(observed_datasets) and declared_datasets == observed_datasets,
        ),
        _check(
            "independent_label_audit",
            bool(document.get("independent_label_audit_verified")),
            True,
            document.get("independent_label_audit_verified") is True,
        ),
        _check(
            "cross_discipline_scope",
            bool(document.get("cross_discipline_scope_verified")),
            True,
            document.get("cross_discipline_scope_verified") is True,
        ),
        _check(
            "custodian_approval",
            bool(approval.get("production_validation_approved")),
            True,
            approval.get("production_validation_approved") is True
            and bool(str(approval.get("reference") or "").strip())
            and _has_timezone_iso8601(approval.get("approved_at")),
        ),
    ]
    failures = [check for check in checks if not check["passed"]]
    return {
        "schema_version": 1,
        "verified": not failures,
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
        "release_scope": (
            "eligible ISTINA identity-gold provenance"
            if not failures
            else "not eligible for ISTINA production-gold gates"
        ),
    }


__all__ = ["assess_istina_provenance"]
