"""Compose provenance-bound ISTINA release evidence without rerunning load tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.istina_deployment_evidence import (
    _load_attachment,
    assess_deployment_evidence,
)
from evaluation.istina_paired_shadow import (
    PairedShadowCriteria,
    assess_paired_shadow,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def revalidate_deployment_inputs(
    gold_readiness: Mapping[str, Any],
    manifest: Mapping[str, Any],
    observed_attachments: Sequence[Mapping[str, Any]],
    *,
    expected_code_revision: str,
) -> Dict[str, Any]:
    dataset_hashes = {
        str(item.get("sha256") or "").lower()
        for item in ((gold_readiness.get("inputs") or {}).get("datasets") or [])
        if isinstance(item, Mapping) and item.get("sha256")
    }
    expected_dataset_sha256 = (
        next(iter(dataset_hashes)) if len(dataset_hashes) == 1 else ""
    )
    result = assess_deployment_evidence(
        manifest,
        observed_attachments,
        expected_dataset_sha256=expected_dataset_sha256,
        expected_code_revision=expected_code_revision,
    )
    result["validation_mode"] = "bundle_raw_attachment_revalidation"
    return result


def revalidate_paired_shadow_inputs(
    gold_readiness: Mapping[str, Any],
    live_shadow: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    expected_code_revision: str,
    expected_plan_sha256: str,
    criteria: PairedShadowCriteria | None = None,
) -> Dict[str, Any]:
    dataset_hashes = {
        str(item.get("sha256") or "").lower()
        for item in ((gold_readiness.get("inputs") or {}).get("datasets") or [])
        if isinstance(item, Mapping) and item.get("sha256")
    }
    expected_dataset_sha256 = (
        next(iter(dataset_hashes)) if len(dataset_hashes) == 1 else ""
    )
    result = assess_paired_shadow(
        live_shadow,
        plan,
        expected_dataset_sha256=expected_dataset_sha256,
        expected_code_revision=expected_code_revision,
        expected_plan_sha256=expected_plan_sha256,
        criteria=criteria,
    )
    result["validation_mode"] = "bundle_raw_shadow_plan_revalidation"
    return result


def compose_evidence_bundle(
    operational: Mapping[str, Any],
    gold_readiness: Mapping[str, Any],
    live_shadow: Optional[Mapping[str, Any]] = None,
    deployment_validation: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge independently generated evidence while preserving fail-closed flags."""

    evidence = dict(operational.get("operational_evidence") or {})
    disciplines = dict(
        ((gold_readiness.get("dataset") or {}).get("disciplines") or {})
    )
    provenance_verified = bool(
        ((gold_readiness.get("provenance") or {}).get("verified"))
    )
    cross_domain_ready = bool(
        gold_readiness.get("data_ready") and provenance_verified
    )
    evidence["cross_domain_gold_verified"] = {
        "verified": cross_domain_ready,
        "provenance_verified": provenance_verified,
        "disciplines": len(disciplines),
        "unresolved_label_issues": int(
            ((gold_readiness.get("adjudication") or {}).get("unresolved") or 0)
        ),
        "reason": (
            "gold-readiness audit passed all sample, coverage, leakage, and "
            "adjudication checks"
            if cross_domain_ready
            else (
                "gold-readiness or ISTINA provenance audit has unresolved "
                "release failures"
            )
        ),
    }
    if live_shadow is not None:
        live_evidence = dict(live_shadow.get("operational_evidence") or {})
        evidence["online_shadow_verified"] = dict(
            live_evidence.get("online_shadow_verified") or {
                "verified": False,
                "reason": "live artifact lacks online shadow evidence",
            }
        )
    else:
        evidence["online_shadow_verified"] = {
            "verified": False,
            "reason": "no live shadow artifact supplied",
        }
    gold_dataset_hashes = {
        str(item.get("sha256") or "").lower()
        for item in ((gold_readiness.get("inputs") or {}).get("datasets") or [])
        if isinstance(item, Mapping) and item.get("sha256")
    }
    deployment_binding = None
    if deployment_validation is not None:
        deployment_document = dict(deployment_validation)
        deployment_manifest = dict(deployment_document.get("manifest") or {})
        deployment_dataset_hash = str(
            deployment_document.get("expected_dataset_sha256") or ""
        ).lower()
        manifest_dataset_hash = str(
            deployment_manifest.get("dataset_sha256") or ""
        ).lower()
        binding_verified = bool(
            deployment_document.get("verified")
            and len(gold_dataset_hashes) == 1
            and deployment_dataset_hash in gold_dataset_hashes
            and manifest_dataset_hash == deployment_dataset_hash
        )
        deployment_binding = {
            "verified": binding_verified,
            "gold_dataset_sha256": (
                next(iter(gold_dataset_hashes))
                if len(gold_dataset_hashes) == 1 else None
            ),
            "deployment_dataset_sha256": deployment_dataset_hash or None,
            "manifest_dataset_sha256": manifest_dataset_hash or None,
            "deployment_validation_verified": bool(
                deployment_document.get("verified")
            ),
            "reason": (
                "validated deployment evidence is bound to the gold dataset"
                if binding_verified
                else (
                    "deployment validation failed or its dataset hash does not "
                    "match the gold-readiness input"
                )
            ),
        }
        deployment_evidence = dict(
            deployment_document.get("operational_evidence") or {}
        )
        externally_verified = (
            "online_shadow_verified",
            "online_load_test_verified",
            "drift_monitoring_verified",
            "durable_audit_retention_verified",
            "paired_shadow_analysis_verified",
        )
        for name in externally_verified:
            item = dict(deployment_evidence.get(name) or {})
            if binding_verified and item.get("verified") is True:
                evidence[name] = item
            else:
                fallback = {
                    "verified": False,
                    "reason": deployment_binding["reason"],
                }
                if name == "online_shadow_verified" and live_shadow is not None:
                    fallback["live_smoke"] = dict(
                        evidence.get("online_shadow_verified") or {}
                    )
                evidence[name] = fallback
        evidence["deployment_validation_verified"] = deployment_binding
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operational_evidence": evidence,
    }
    if deployment_binding is not None:
        result["deployment_binding"] = deployment_binding
    return result


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected a JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operational-validation", type=Path, required=True)
    parser.add_argument("--gold-readiness", type=Path, required=True)
    parser.add_argument("--live-shadow", type=Path)
    parser.add_argument("--deployment-manifest", type=Path)
    parser.add_argument("--deployment-attachment", type=Path, nargs="+")
    parser.add_argument("--paired-shadow-plan", type=Path)
    parser.add_argument("--expected-code-revision")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    operational = _load(args.operational_validation)
    gold_readiness = _load(args.gold_readiness)
    live_shadow = _load(args.live_shadow) if args.live_shadow else None
    raw_deployment_requested = bool(
        args.deployment_manifest
        or args.deployment_attachment
        or args.paired_shadow_plan
        or args.expected_code_revision
    )
    if raw_deployment_requested and not (
        args.deployment_manifest
        and args.deployment_attachment
        and args.paired_shadow_plan
        and args.expected_code_revision
        and args.live_shadow
    ):
        parser.error(
            "--live-shadow, --deployment-manifest, --deployment-attachment, "
            "--paired-shadow-plan, and --expected-code-revision are required together"
        )
    if raw_deployment_requested:
        deployment_validation = revalidate_deployment_inputs(
            gold_readiness,
            _load(args.deployment_manifest),
            [_load_attachment(path) for path in args.deployment_attachment],
            expected_code_revision=args.expected_code_revision,
        )
        paired_shadow = revalidate_paired_shadow_inputs(
            gold_readiness,
            live_shadow,
            _load(args.paired_shadow_plan),
            expected_code_revision=args.expected_code_revision,
            expected_plan_sha256=sha256_file(args.paired_shadow_plan),
        )
        deployment_validation["paired_shadow_analysis"] = paired_shadow
        deployment_validation["operational_evidence"][
            "paired_shadow_analysis_verified"
        ] = dict(
            (paired_shadow.get("operational_evidence") or {}).get(
                "paired_shadow_analysis_verified"
            )
            or {"verified": False}
        )
    else:
        deployment_validation = None
    result = compose_evidence_bundle(
        operational,
        gold_readiness,
        live_shadow,
        deployment_validation,
    )
    sources = {
        "operational_validation": args.operational_validation,
        "gold_readiness": args.gold_readiness,
    }
    if args.live_shadow:
        sources["live_shadow"] = args.live_shadow
    if raw_deployment_requested:
        sources["deployment_manifest"] = args.deployment_manifest
        sources["paired_shadow_plan"] = args.paired_shadow_plan
        for index, path in enumerate(args.deployment_attachment, start=1):
            sources[f"deployment_attachment_{index}"] = path
    result["sources"] = {
        name: {"name": path.name, "sha256": sha256_file(path)}
        for name, path in sources.items()
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    verified = sum(
        bool(value.get("verified")) if isinstance(value, Mapping) else bool(value)
        for value in result["operational_evidence"].values()
    )
    print(json.dumps({
        "output": str(args.output),
        "verified_operational_items": verified,
        "total_operational_items": len(result["operational_evidence"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = [
    "compose_evidence_bundle",
    "revalidate_deployment_inputs",
    "revalidate_paired_shadow_inputs",
]
