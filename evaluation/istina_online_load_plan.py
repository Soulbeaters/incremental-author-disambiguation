"""Validate an immutable institutional ISTINA online-load plan.

The plan binds every value that can change service load.  Validation is safe
to run before the approved window; the load runner repeats it with the active
window requirement immediately before it creates any service requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping


INSTITUTIONAL_LOAD_SCOPE = "institutional_load_window"
ONLINE_LOAD_MODE = "read_only_candidate_lookup"
ONLINE_LOAD_PURPOSE = "approved_institutional_read_only_load"
APPROVER_ROLES = {"service_owner", "operations", "service_owner_and_operations"}
_USE_CURRENT_TIME = object()


@dataclass(frozen=True)
class OnlineLoadPlanCriteria:
    min_requests: int = 1_000
    min_concurrency: int = 1
    max_concurrency: int = 16
    min_rps: float = 0.1
    max_rps: float = 20.0
    min_timeout_seconds: float = 0.1
    max_timeout_seconds: float = 120.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def man_id_sha256(man_id: int) -> str:
    return sha256_text(f"istina-man-id-v1:{man_id}")


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
    number = float(value)
    return number if math.isfinite(number) else None


def _check(
    name: str,
    observed: Any,
    required: Any,
    passed: bool,
) -> Dict[str, Any]:
    return {
        "name": name,
        "category": "online_load_plan",
        "observed": observed,
        "required": required,
        "passed": bool(passed),
    }


def _same_number(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    return bool(
        left_number is not None
        and right_number is not None
        and abs(left_number - right_number) <= tolerance
    )


def assess_online_load_plan(
    plan: Mapping[str, Any] | None,
    *,
    expected_dataset_sha256: str,
    expected_code_revision: str,
    expected_service_url_sha256: str,
    expected_man_id_sha256: str,
    expected_requests: int,
    expected_concurrency: int,
    expected_max_rps: float,
    expected_service_timeout_seconds: float,
    expected_change_reference: str,
    validation_time: datetime | None | object = _USE_CURRENT_TIME,
    require_active_window: bool = False,
    criteria: OnlineLoadPlanCriteria | None = None,
) -> Dict[str, Any]:
    """Recompute plan validity against the exact proposed execution."""

    criteria = criteria or OnlineLoadPlanCriteria()
    document = dict(plan or {})
    window = (
        dict(document.get("window") or {})
        if isinstance(document.get("window"), Mapping)
        else {}
    )
    approval = (
        dict(document.get("approval") or {})
        if isinstance(document.get("approval"), Mapping)
        else {}
    )
    start = _timestamp(window.get("start"))
    end = _timestamp(window.get("end"))
    approved_at = _timestamp(approval.get("approved_at"))
    if validation_time is _USE_CURRENT_TIME:
        cutoff = datetime.now(timezone.utc)
    elif isinstance(validation_time, datetime) and validation_time.tzinfo is not None:
        cutoff = validation_time
    else:
        cutoff = None

    dataset_sha = str(document.get("dataset_sha256") or "").lower()
    code_revision = str(document.get("code_revision") or "").lower()
    service_url_hash = str(document.get("service_url_sha256") or "").lower()
    man_id_hash = str(document.get("man_id_sha256") or "").lower()
    expected_dataset_sha256 = str(expected_dataset_sha256 or "").lower()
    expected_code_revision = str(expected_code_revision or "").lower()
    expected_service_url_sha256 = str(expected_service_url_sha256 or "").lower()
    expected_man_id_sha256 = str(expected_man_id_sha256 or "").lower()
    requests = document.get("requests")
    concurrency = document.get("concurrency")
    max_rps = document.get("max_rps")
    timeout = document.get("service_timeout_seconds")
    plan_id = document.get("plan_id")
    change_reference = approval.get("change_reference")
    approver_role = approval.get("approver_role")
    window_ordered = bool(start is not None and end is not None and start < end)
    approval_precedes_window = bool(
        approved_at is not None
        and start is not None
        and cutoff is not None
        and approved_at <= start
        and approved_at <= cutoff
    )
    not_expired = bool(cutoff is not None and end is not None and cutoff <= end)
    active_window = bool(
        cutoff is not None
        and start is not None
        and end is not None
        and start <= cutoff <= end
    )

    checks = [
        _check("schema_version", document.get("schema_version"), 1, type(document.get("schema_version")) is int and document.get("schema_version") == 1),
        _check("source_system", document.get("source_system"), "istina", document.get("source_system") == "istina"),
        _check("purpose", document.get("purpose"), ONLINE_LOAD_PURPOSE, document.get("purpose") == ONLINE_LOAD_PURPOSE),
        _check("mode", document.get("mode"), ONLINE_LOAD_MODE, document.get("mode") == ONLINE_LOAD_MODE),
        _check("plan_id", plan_id, "non-empty string", isinstance(plan_id, str) and bool(plan_id.strip())),
        _check("dataset_sha256", dataset_sha, expected_dataset_sha256, re.fullmatch(r"[0-9a-f]{64}", expected_dataset_sha256) is not None and dataset_sha == expected_dataset_sha256),
        _check("code_revision", code_revision, expected_code_revision, re.fullmatch(r"[0-9a-f]{40}", expected_code_revision) is not None and code_revision == expected_code_revision),
        _check("service_url_sha256", service_url_hash, expected_service_url_sha256, re.fullmatch(r"[0-9a-f]{64}", expected_service_url_sha256) is not None and service_url_hash == expected_service_url_sha256),
        _check("man_id_sha256", man_id_hash, expected_man_id_sha256, re.fullmatch(r"[0-9a-f]{64}", expected_man_id_sha256) is not None and man_id_hash == expected_man_id_sha256),
        _check("requests", requests, expected_requests, type(requests) is int and requests >= criteria.min_requests and requests == expected_requests),
        _check("concurrency", concurrency, expected_concurrency, type(concurrency) is int and criteria.min_concurrency <= concurrency <= criteria.max_concurrency and concurrency == expected_concurrency),
        _check("max_rps", max_rps, expected_max_rps, _number(max_rps) is not None and criteria.min_rps <= float(max_rps) <= criteria.max_rps and _same_number(max_rps, expected_max_rps)),
        _check("service_timeout_seconds", timeout, expected_service_timeout_seconds, _number(timeout) is not None and criteria.min_timeout_seconds <= float(timeout) <= criteria.max_timeout_seconds and _same_number(timeout, expected_service_timeout_seconds)),
        _check("window", window, "timezone-aware start < end", window_ordered),
        _check("approval_precedes_window", approval.get("approved_at"), "timezone-aware approval at or before both validation and window start", approval_precedes_window),
        _check("window_not_expired", window.get("end"), "validation time at or before window end", not_expired),
        _check("active_window", active_window, require_active_window, active_window if require_active_window else True),
        _check("approval_scope", approval.get("scope"), INSTITUTIONAL_LOAD_SCOPE, approval.get("scope") == INSTITUTIONAL_LOAD_SCOPE),
        _check("approved", approval.get("approved"), True, approval.get("approved") is True),
        _check("change_reference", change_reference, expected_change_reference, isinstance(change_reference, str) and bool(change_reference.strip()) and change_reference == expected_change_reference),
        _check("approver_role", approver_role, sorted(APPROVER_ROLES), approver_role in APPROVER_ROLES),
    ]
    failures = [item for item in checks if not item["passed"]]
    return {
        "schema_version": 1,
        "verified": not failures,
        "require_active_window": require_active_window,
        "validation_time": cutoff.isoformat() if cutoff is not None else None,
        "approved_window": {
            "start": start.isoformat() if start is not None else None,
            "end": end.isoformat() if end is not None else None,
        },
        "criteria": asdict(criteria),
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
    }


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-dataset", type=Path, required=True)
    parser.add_argument("--expected-code-revision", required=True)
    parser.add_argument("--service-url", required=True)
    parser.add_argument("--man-id", type=int, required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--max-rps", type=float, required=True)
    parser.add_argument("--service-timeout", type=float, required=True)
    parser.add_argument("--approved-change-reference", required=True)
    parser.add_argument("--require-active-window", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = assess_online_load_plan(
        _load(args.plan),
        expected_dataset_sha256=sha256_file(args.expected_dataset),
        expected_code_revision=args.expected_code_revision,
        expected_service_url_sha256=sha256_text(args.service_url),
        expected_man_id_sha256=man_id_sha256(args.man_id),
        expected_requests=args.requests,
        expected_concurrency=args.concurrency,
        expected_max_rps=args.max_rps,
        expected_service_timeout_seconds=args.service_timeout,
        expected_change_reference=args.approved_change_reference,
        require_active_window=args.require_active_window,
    )
    result["inputs"] = {
        "plan": {"name": args.plan.name, "sha256": sha256_file(args.plan)},
        "dataset": {
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
        "failed_checks": result["summary"]["failed"],
        "plan_sha256": sha256_file(args.plan),
    }, ensure_ascii=False))
    if not result["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "APPROVER_ROLES",
    "INSTITUTIONAL_LOAD_SCOPE",
    "ONLINE_LOAD_MODE",
    "ONLINE_LOAD_PURPOSE",
    "OnlineLoadPlanCriteria",
    "assess_online_load_plan",
    "man_id_sha256",
    "sha256_file",
    "sha256_text",
]
