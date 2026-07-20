"""Durable, tamper-evident and privacy-preserving ISTINA audit records.

The JSONL sink is intentionally single-process.  Deployments with multiple
workers must allocate one file per worker or replace it with a transactional
central append service implementing the same callable/durable contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, Mapping


GENESIS_HASH = "0" * 64
MAX_AUDIT_LINE_CHARACTERS = 65_536
FORBIDDEN_EVENT_FIELDS = {
    "name",
    "original_name",
    "article_id",
    "doi",
    "title",
    "affiliation",
    "author_id",
}
ALLOWED_EVENT_FIELDS = {
    "schema_version",
    "article_id_hash",
    "name_hash",
    "position",
    "decision",
    "author_id_hash",
    "stage",
    "deterministic_hash",
    "candidate_count",
    "candidate_pool_truncated",
    "latency_ms",
    "service_error",
    "requested_mode",
    "effective_mode",
    "write_authorized",
    "idempotency_key",
    "monitor_status",
    "monitor_alert",
    "rollback_reason",
    "circuit_state",
}
REQUIRED_EVENT_FIELDS = ALLOWED_EVENT_FIELDS


class AuditIntegrityError(RuntimeError):
    """Raised when an audit record is invalid, unredacted, or corrupted."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AuditIntegrityError(f"audit value is not canonical JSON: {exc}") from exc


def _is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_redacted_event(event: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, Mapping):
        raise AuditIntegrityError("audit event must be a mapping")
    keys = set(event)
    forbidden = sorted(keys & FORBIDDEN_EVENT_FIELDS)
    if forbidden:
        raise AuditIntegrityError(
            "raw identifier fields are forbidden in audit events: " + ", ".join(forbidden)
        )
    unknown = sorted(keys - ALLOWED_EVENT_FIELDS)
    if unknown:
        raise AuditIntegrityError("unknown audit event fields: " + ", ".join(unknown))
    missing = sorted(REQUIRED_EVENT_FIELDS - keys)
    if missing:
        raise AuditIntegrityError("missing audit event fields: " + ", ".join(missing))
    if event.get("schema_version") != 1:
        raise AuditIntegrityError("unsupported audit event schema_version")
    for field in ("article_id_hash", "name_hash"):
        if not _is_hex(event.get(field), 16):
            raise AuditIntegrityError(f"{field} must be a 16-character lowercase hash")
    deterministic_hash = event.get("deterministic_hash")
    if not _is_hex(deterministic_hash, 16):
        raise AuditIntegrityError(
            "deterministic_hash must be a 16-character lowercase hash"
        )
    author_hash = event.get("author_id_hash")
    if author_hash is not None and not _is_hex(author_hash, 16):
        raise AuditIntegrityError("author_id_hash must be null or a 16-character lowercase hash")
    idempotency_key = event.get("idempotency_key")
    if idempotency_key is not None and not _is_hex(idempotency_key, 64):
        raise AuditIntegrityError("idempotency_key must be null or a 64-character lowercase hash")
    latency = event.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)):
        raise AuditIntegrityError("latency_ms must be numeric")
    if not math.isfinite(float(latency)) or float(latency) < 0:
        raise AuditIntegrityError("latency_ms must be finite and non-negative")
    candidate_count = event.get("candidate_count")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
    ):
        raise AuditIntegrityError("candidate_count must be a non-negative integer")
    for field in (
        "candidate_pool_truncated",
        "service_error",
        "write_authorized",
        "monitor_alert",
    ):
        if not isinstance(event.get(field), bool):
            raise AuditIntegrityError(f"{field} must be boolean")
    position = event.get("position")
    if not isinstance(position, str) or not (
        position == "unknown" or position.isdigit()
    ):
        raise AuditIntegrityError("position must be a numeric string or unknown")
    if event.get("decision") not in {"merge", "new", "unknown"}:
        raise AuditIntegrityError("decision must be merge, new, or unknown")
    if event.get("requested_mode") not in {"shadow", "candidate", "write"}:
        raise AuditIntegrityError("requested_mode is invalid")
    if event.get("effective_mode") not in {"shadow", "candidate", "write"}:
        raise AuditIntegrityError("effective_mode is invalid")
    if event.get("circuit_state") not in {"closed", "open", "half_open"}:
        raise AuditIntegrityError("circuit_state is invalid")
    if event.get("rollback_reason") not in {
        None,
        "legacy_service_error",
        "decision_drift_alert",
        "legacy_service_circuit_open",
        "manual_or_unspecified_rollback",
    }:
        raise AuditIntegrityError("rollback_reason must use a redacted category")
    stage = event.get("stage")
    if not isinstance(stage, str) or not re.fullmatch(r"[a-z0-9_.:-]{1,64}", stage):
        raise AuditIntegrityError("stage must be a bounded machine category")
    if event.get("monitor_status") not in {
        "disabled",
        "empty",
        "warming_up",
        "healthy",
        "alert",
        "unknown",
    }:
        raise AuditIntegrityError("monitor_status is invalid")
    return dict(event)


def _record_hash(sequence: int, previous_hash: str, event: Mapping[str, Any]) -> str:
    payload = {
        "event": dict(event),
        "previous_hash": previous_hash,
        "sequence": sequence,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def verify_audit_chain(path: Path | str) -> Dict[str, Any]:
    """Stream-verify a JSONL chain without returning sensitive event content."""

    audit_path = Path(path)
    if not audit_path.exists():
        return {
            "verified": True,
            "records": 0,
            "head_hash": GENESIS_HASH,
        }
    previous_hash = GENESIS_HASH
    records = 0
    with audit_path.open("r", encoding="utf-8") as handle:
        line_number = 0
        while True:
            raw_line = handle.readline(MAX_AUDIT_LINE_CHARACTERS + 1)
            if not raw_line:
                break
            line_number += 1
            if len(raw_line) > MAX_AUDIT_LINE_CHARACTERS:
                raise AuditIntegrityError(f"oversized audit record at line {line_number}")
            if not raw_line.endswith("\n"):
                raise AuditIntegrityError(f"incomplete audit record at line {line_number}")
            if not raw_line.strip():
                raise AuditIntegrityError(f"blank audit record at line {line_number}")
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise AuditIntegrityError(
                    f"invalid audit JSON at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(record, dict) or set(record) != {
                "sequence",
                "previous_hash",
                "event",
                "record_hash",
            }:
                raise AuditIntegrityError(f"invalid audit envelope at line {line_number}")
            sequence = record.get("sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != records + 1
            ):
                raise AuditIntegrityError(f"non-contiguous sequence at line {line_number}")
            if record.get("previous_hash") != previous_hash:
                raise AuditIntegrityError(f"previous hash mismatch at line {line_number}")
            event = _validate_redacted_event(record.get("event"))
            expected_hash = _record_hash(sequence, previous_hash, event)
            if record.get("record_hash") != expected_hash:
                raise AuditIntegrityError(f"record hash mismatch at line {line_number}")
            previous_hash = expected_hash
            records += 1
    return {
        "verified": True,
        "records": records,
        "head_hash": previous_hash,
    }


class TamperEvidentJsonlAuditSink:
    """Append-only JSONL audit sink with hash chaining and optional fsync."""

    def __init__(self, path: Path | str, fsync: bool = True) -> None:
        self.path = Path(path)
        self.fsync = bool(fsync)
        self.durable = self.fsync
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = verify_audit_chain(self.path)
        self._records = int(state["records"])
        self._head_hash = str(state["head_hash"])

    def __call__(self, event: Mapping[str, Any]) -> None:
        redacted_event = _validate_redacted_event(event)
        with self._lock:
            sequence = self._records + 1
            record_hash = _record_hash(sequence, self._head_hash, redacted_event)
            record = {
                "sequence": sequence,
                "previous_hash": self._head_hash,
                "event": redacted_event,
                "record_hash": record_hash,
            }
            encoded = (_canonical_json(record) + "\n").encode("utf-8")
            with self.path.open("ab", buffering=0) as handle:
                written = handle.write(encoded)
                if written != len(encoded):
                    raise OSError("partial audit append")
                if self.fsync:
                    os.fsync(handle.fileno())
            self._records = sequence
            self._head_hash = record_hash

    def snapshot(self) -> Dict[str, Any]:
        return {
            "durable": self.durable,
            "records": self._records,
            "head_hash": self._head_hash,
            "fsync": self.fsync,
        }


__all__ = [
    "AuditIntegrityError",
    "GENESIS_HASH",
    "MAX_AUDIT_LINE_CHARACTERS",
    "TamperEvidentJsonlAuditSink",
    "verify_audit_chain",
]
