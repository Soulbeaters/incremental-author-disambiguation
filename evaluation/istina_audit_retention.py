"""Build machine-verified ISTINA durable-audit retention evidence.

The command stream-verifies one private JSONL hash chain per worker and binds
each chain to the retained, fsync-enabled shadow telemetry that produced it.
Only aggregate hashes and counts are emitted; audit events and private paths
remain outside the evidence artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from integrations.istina_observability import verify_audit_chain  # noqa: E402


AUDIT_RETENTION_METHOD = "istina_audit_retention_v1"
AUDIT_CHAIN_MANIFEST_ALGORITHM = "sha256_canonical_worker_chain_manifest_v1"
AUDIT_HEAD_HASH_SCOPE = "aggregate_chain_manifest"
MIN_RETENTION_DAYS = 90
CHAIN_ENTRY_FIELDS = {
    "chain_sha256",
    "telemetry_sha256",
    "records",
    "head_hash",
}


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


def audit_chain_manifest_sha256(
    chain_entries: Sequence[Mapping[str, Any]],
) -> str:
    payload = {
        "algorithm": AUDIT_CHAIN_MANIFEST_ALGORITHM,
        "chains": [dict(entry) for entry in chain_entries],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected a JSON object in {path}")
    return dict(document)


def _full_hex(value: Any, length: int) -> bool:
    return re.fullmatch(rf"[0-9a-f]{{{length}}}", str(value or "")) is not None


def _validated_paths(paths: Sequence[Path], role: str) -> list[Path]:
    if not paths:
        raise ValueError(f"at least one {role} file is required")
    resolved: list[Path] = []
    for path in paths:
        candidate = path.resolve(strict=True)
        if path.is_symlink() or not candidate.is_file():
            raise ValueError(f"{role} must be a regular non-symlink file: {path}")
        resolved.append(candidate)
    if len(set(resolved)) != len(resolved):
        raise ValueError(f"duplicate {role} path")
    return resolved


def _telemetry_binding(
    document: Mapping[str, Any],
    *,
    dataset_sha256: str,
    code_revision: str,
) -> Dict[str, Any]:
    protocol = dict(document.get("protocol") or {})
    safety = dict(document.get("safety") or {})
    chain = dict(safety.get("durable_audit_chain") or {})
    if document.get("schema_version") != 1:
        raise ValueError("shadow telemetry schema_version must be 1")
    if str(protocol.get("dataset_sha256") or "").lower() != dataset_sha256:
        raise ValueError("shadow telemetry dataset SHA-256 mismatch")
    if str(protocol.get("code_revision") or "").lower() != code_revision:
        raise ValueError("shadow telemetry code revision mismatch")
    if protocol.get("mode") != "shadow":
        raise ValueError("audit telemetry must come from shadow mode")
    if chain.get("verified") is not True:
        raise ValueError("shadow telemetry does not verify its audit chain")
    if chain.get("retained") is not True:
        raise ValueError("ephemeral audit telemetry cannot prove retention")
    if chain.get("fsync") is not True:
        raise ValueError("audit telemetry must declare fsync durability")
    records = chain.get("chain_records_total")
    if isinstance(records, bool) or not isinstance(records, int) or records <= 0:
        raise ValueError("shadow telemetry audit record count must be positive")
    head_hash = str(chain.get("head_hash") or "").lower()
    if not _full_hex(head_hash, 64):
        raise ValueError("shadow telemetry audit head must be 64-hex")
    return {"records": records, "head_hash": head_hash}


def build_audit_retention_evidence(
    *,
    audit_chains: Sequence[Path],
    shadow_telemetry: Sequence[Path],
    dataset_sha256: str,
    code_revision: str,
    retention_days: int,
    storage_reference: str,
    retention_policy_reference: str,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    dataset_sha256 = str(dataset_sha256 or "").lower()
    code_revision = str(code_revision or "").lower()
    if not _full_hex(dataset_sha256, 64):
        raise ValueError("dataset-sha256 must be 64 lowercase hex characters")
    if not _full_hex(code_revision, 40):
        raise ValueError("code-revision must be a full lowercase 40-hex commit")
    if (
        isinstance(retention_days, bool)
        or not isinstance(retention_days, int)
        or retention_days < MIN_RETENTION_DAYS
    ):
        raise ValueError(
            f"retention-days must be at least {MIN_RETENTION_DAYS}"
        )
    storage_reference = str(storage_reference or "").strip()
    retention_policy_reference = str(retention_policy_reference or "").strip()
    if not storage_reference or not retention_policy_reference:
        raise ValueError("storage and retention-policy references are required")

    chain_paths = _validated_paths(audit_chains, "audit chain")
    telemetry_paths = _validated_paths(shadow_telemetry, "shadow telemetry")
    if len(chain_paths) != len(telemetry_paths):
        raise ValueError("one retained shadow telemetry file is required per chain")
    if set(chain_paths) & set(telemetry_paths):
        raise ValueError("audit chains and telemetry must be distinct files")

    chains: list[Dict[str, Any]] = []
    for path in chain_paths:
        report = verify_audit_chain(path)
        if report.get("verified") is not True or int(report.get("records") or 0) <= 0:
            raise ValueError("audit chains must be verified and non-empty")
        chains.append({
            "chain_sha256": sha256_file(path),
            "records": int(report["records"]),
            "head_hash": str(report["head_hash"]).lower(),
        })
    if len({item["chain_sha256"] for item in chains}) != len(chains):
        raise ValueError("duplicate audit chain content")
    if len({item["head_hash"] for item in chains}) != len(chains):
        raise ValueError("audit chain heads must be unique per worker")

    telemetry: list[Dict[str, Any]] = []
    for path in telemetry_paths:
        binding = _telemetry_binding(
            _load_json(path),
            dataset_sha256=dataset_sha256,
            code_revision=code_revision,
        )
        telemetry.append({
            **binding,
            "telemetry_sha256": sha256_file(path),
        })
    if len({item["telemetry_sha256"] for item in telemetry}) != len(telemetry):
        raise ValueError("duplicate shadow telemetry content")
    telemetry_by_head = {item["head_hash"]: item for item in telemetry}
    if len(telemetry_by_head) != len(telemetry):
        raise ValueError("shadow telemetry audit heads must be unique")

    entries = []
    for chain in chains:
        bound = telemetry_by_head.get(chain["head_hash"])
        if bound is None or bound["records"] != chain["records"]:
            raise ValueError("audit chain does not match retained shadow telemetry")
        entries.append({
            "chain_sha256": chain["chain_sha256"],
            "telemetry_sha256": bound["telemetry_sha256"],
            "records": chain["records"],
            "head_hash": chain["head_hash"],
        })
    entries.sort(key=lambda item: item["chain_sha256"])
    manifest_sha256 = audit_chain_manifest_sha256(entries)

    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed_timestamp.tzinfo is None:
        raise ValueError("generated-at must be timezone-aware")
    return {
        "schema_version": 1,
        "source_system": "istina",
        "dataset_sha256": dataset_sha256,
        "code_revision": code_revision,
        "generated_at": timestamp,
        "verification": {
            "durable": True,
            "chain_verified": True,
            "retention_days": retention_days,
            "records": sum(item["records"] for item in entries),
            "head_hash": manifest_sha256,
            "head_hash_scope": AUDIT_HEAD_HASH_SCOPE,
            "verification_method": AUDIT_RETENTION_METHOD,
            "chain_count": len(entries),
            "telemetry_count": len(telemetry),
            "chain_manifest_algorithm": AUDIT_CHAIN_MANIFEST_ALGORITHM,
            "chain_manifest_sha256": manifest_sha256,
            "telemetry_binding_verified": True,
            "record_level_content_included": False,
            "chain_entries": entries,
            "storage_reference": storage_reference,
            "retention_policy_reference": retention_policy_reference,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-chain", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--shadow-telemetry",
        type=Path,
        nargs="+",
        required=True,
        help="Retained live-shadow JSON files, one for each worker chain.",
    )
    parser.add_argument("--dataset-sha256", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--retention-days", type=int, required=True)
    parser.add_argument("--storage-reference", required=True)
    parser.add_argument("--retention-policy-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_audit_retention_evidence(
        audit_chains=args.audit_chain,
        shadow_telemetry=args.shadow_telemetry,
        dataset_sha256=args.dataset_sha256,
        code_revision=args.code_revision,
        retention_days=args.retention_days,
        storage_reference=args.storage_reference,
        retention_policy_reference=args.retention_policy_reference,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    verification = result["verification"]
    print(json.dumps({
        "output": str(args.output),
        "chain_verified": verification["chain_verified"],
        "chain_count": verification["chain_count"],
        "records": verification["records"],
        "chain_manifest_sha256": verification["chain_manifest_sha256"],
        "record_level_content_included": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
