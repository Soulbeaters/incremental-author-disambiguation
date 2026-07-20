"""Aggregate frozen ISTINA offline-load trials without cherry-picking.

Every input must use the same dataset, code revision, split, operation count,
environment fingerprint, and unchanged all-operation p95 method.  At least
three sequential trials are required and every trial must pass.  The output
contains hashes and aggregate performance values, never private record data or
local paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.istina_operational_validation import (
    OFFLINE_LOAD_P95_LIMIT_MS,
    OFFLINE_LOAD_VERIFICATION_METHOD,
)
from experiments.istina_runtime_replay import percentile


METHOD = "istina_offline_performance_repeatability_v1"
MIN_TRIALS = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _full_hex(value: Any, length: int) -> bool:
    return re.fullmatch(rf"[0-9a-f]{{{length}}}", str(value or "")) is not None


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _load_json(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected a JSON object in {path}")
    return dict(document)


def build_performance_reproducibility(
    *,
    trials: Sequence[Mapping[str, Any]],
    trial_sha256s: Sequence[str],
    expected_dataset_sha256: str,
    expected_code_revision: str,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    expected_dataset_sha256 = str(expected_dataset_sha256 or "").lower()
    expected_code_revision = str(expected_code_revision or "").lower()
    if not _full_hex(expected_dataset_sha256, 64):
        raise ValueError("expected dataset SHA-256 must be 64 lowercase hex")
    if not _full_hex(expected_code_revision, 40):
        raise ValueError("expected code revision must be a full 40-hex commit")
    if len(trials) < MIN_TRIALS or len(trials) != len(trial_sha256s):
        raise ValueError(f"at least {MIN_TRIALS} trials and matching hashes are required")
    normalized_hashes = [str(value or "").lower() for value in trial_sha256s]
    if not all(_full_hex(value, 64) for value in normalized_hashes):
        raise ValueError("trial hashes must be 64 lowercase hex")
    if len(set(normalized_hashes)) != len(normalized_hashes):
        raise ValueError("duplicate trial content is not independent evidence")

    entries = []
    trial_ids = set()
    common_protocol: tuple[Any, ...] | None = None
    environment_sha256: str | None = None
    for document, source_sha256 in zip(trials, normalized_hashes):
        protocol = dict(document.get("protocol") or {})
        operational = dict(document.get("operational_validation") or {})
        load = dict(operational.get("offline_load_test") or {})
        environment = dict(load.get("environment") or {})
        trial_id = str(protocol.get("performance_trial_id") or "")
        if document.get("schema_version") != 1:
            raise ValueError("trial schema_version must be 1")
        if protocol.get("dataset_sha256") != expected_dataset_sha256:
            raise ValueError("trial dataset SHA-256 mismatch")
        if protocol.get("code_revision") != expected_code_revision:
            raise ValueError("trial code revision mismatch")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", trial_id) is None:
            raise ValueError("trial ID is missing or invalid")
        if trial_id in trial_ids:
            raise ValueError("trial IDs must be unique")
        trial_ids.add(trial_id)

        iterations = protocol.get("load_iterations")
        test_mentions = protocol.get("test_mentions")
        operations = load.get("load_operations")
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or iterations <= 0
            or isinstance(test_mentions, bool)
            or not isinstance(test_mentions, int)
            or test_mentions <= 0
            or operations != iterations * test_mentions
        ):
            raise ValueError("trial operation counts are inconsistent")
        identity = (
            protocol.get("split_strategy"),
            protocol.get("train_through_year"),
            test_mentions,
            iterations,
            operations,
            load.get("verification_method"),
            load.get("acceptance_threshold_ms_p95"),
        )
        if common_protocol is None:
            common_protocol = identity
        elif identity != common_protocol:
            raise ValueError("trial protocols are not identical")
        if load.get("verification_method") != OFFLINE_LOAD_VERIFICATION_METHOD:
            raise ValueError("unexpected offline-load verification method")
        if load.get("acceptance_threshold_ms_p95") != OFFLINE_LOAD_P95_LIMIT_MS:
            raise ValueError("offline-load threshold changed between trials")

        p95 = load.get("latency_ms_p95")
        throughput = load.get("throughput_mentions_per_second")
        iteration_p95 = list(load.get("iteration_latency_ms_p95") or [])
        if (
            not _finite_number(p95)
            or float(p95) < 0.0
            or not _finite_number(throughput)
            or float(throughput) <= 0.0
            or len(iteration_p95) != iterations
            or not all(_finite_number(value) and value >= 0.0 for value in iteration_p95)
        ):
            raise ValueError("trial latency metrics are missing or non-finite")
        summary = dict(load.get("iteration_p95_summary_ms") or {})
        expected_summary = {
            "minimum": min(iteration_p95),
            "median": percentile(iteration_p95, 0.50),
            "maximum": max(iteration_p95),
            "passing_iterations": sum(
                value <= OFFLINE_LOAD_P95_LIMIT_MS for value in iteration_p95
            ),
            "total_iterations": iterations,
        }
        if summary != expected_summary:
            raise ValueError("trial iteration summary does not match its samples")
        mismatches = load.get("deterministic_hash_mismatches")
        recomputed_verified = bool(
            mismatches == 0 and float(p95) <= OFFLINE_LOAD_P95_LIMIT_MS
        )
        if load.get("verified") is not recomputed_verified:
            raise ValueError("trial verified flag does not match the fixed rule")
        margin = load.get("threshold_margin_ms")
        if not _finite_number(margin) or not math.isclose(
            float(margin),
            OFFLINE_LOAD_P95_LIMIT_MS - float(p95),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("trial threshold margin is inconsistent")
        if environment.get("host_identifier_included") is not False:
            raise ValueError("environment evidence must exclude host identifiers")
        current_environment_sha256 = _canonical_sha256(environment)
        if environment_sha256 is None:
            environment_sha256 = current_environment_sha256
        elif current_environment_sha256 != environment_sha256:
            raise ValueError("trial environments differ")

        entries.append({
            "trial_id": trial_id,
            "source_sha256": source_sha256,
            "verified": recomputed_verified,
            "latency_ms_p95": float(p95),
            "threshold_margin_ms": float(margin),
            "throughput_mentions_per_second": float(throughput),
            "iteration_p95_minimum_ms": float(expected_summary["minimum"]),
            "iteration_p95_median_ms": float(expected_summary["median"]),
            "iteration_p95_maximum_ms": float(expected_summary["maximum"]),
            "passing_iterations": expected_summary["passing_iterations"],
            "total_iterations": iterations,
        })

    entries.sort(key=lambda item: item["trial_id"])
    p95_values = [item["latency_ms_p95"] for item in entries]
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed_timestamp.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    verified = all(item["verified"] for item in entries)
    return {
        "schema_version": 1,
        "generated_at": timestamp,
        "method": METHOD,
        "protocol": {
            "source_system": "istina",
            "dataset_sha256": expected_dataset_sha256,
            "code_revision": expected_code_revision,
            "minimum_trials": MIN_TRIALS,
            "trial_count": len(entries),
            "verification_method": OFFLINE_LOAD_VERIFICATION_METHOD,
            "acceptance_threshold_ms_p95": OFFLINE_LOAD_P95_LIMIT_MS,
            "all_trials_must_pass": True,
            "environment_sha256": environment_sha256,
            "host_identifier_included": False,
        },
        "summary": {
            "verified": verified,
            "passing_trials": sum(item["verified"] for item in entries),
            "failed_trials": sum(not item["verified"] for item in entries),
            "trial_count": len(entries),
            "combined_replay_operations": sum(
                int(common_protocol[4]) for _item in entries
            ),
        },
        "metrics": {
            "trial_p95_ms": p95_values,
            "trial_p95_minimum_ms": min(p95_values),
            "trial_p95_median_ms": percentile(p95_values, 0.50),
            "trial_p95_maximum_ms": max(p95_values),
            "trial_p95_range_ms": max(p95_values) - min(p95_values),
        },
        "trials": entries,
        "release_constraints": {
            "repeated_operations_are_distinct_gold": False,
            "write_enabled_replacement_authorized": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, nargs="+", required=True)
    parser.add_argument("--expected-dataset", type=Path, required=True)
    parser.add_argument("--expected-code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_performance_reproducibility(
        trials=[_load_json(path) for path in args.trial],
        trial_sha256s=[sha256_file(path) for path in args.trial],
        expected_dataset_sha256=sha256_file(args.expected_dataset),
        expected_code_revision=args.expected_code_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "verified": result["summary"]["verified"],
        "passing_trials": result["summary"]["passing_trials"],
        "trial_count": result["summary"]["trial_count"],
        "trial_p95_median_ms": result["metrics"]["trial_p95_median_ms"],
        "trial_p95_maximum_ms": result["metrics"]["trial_p95_maximum_ms"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
