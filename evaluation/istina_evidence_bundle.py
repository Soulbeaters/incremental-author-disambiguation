"""Compose provenance-bound ISTINA release evidence without rerunning load tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compose_evidence_bundle(
    operational: Mapping[str, Any],
    gold_readiness: Mapping[str, Any],
    live_shadow: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge independently generated evidence while preserving fail-closed flags."""

    evidence = dict(operational.get("operational_evidence") or {})
    disciplines = dict(
        ((gold_readiness.get("dataset") or {}).get("disciplines") or {})
    )
    evidence["cross_domain_gold_verified"] = {
        "verified": bool(gold_readiness.get("data_ready")),
        "disciplines": len(disciplines),
        "unresolved_label_issues": int(
            ((gold_readiness.get("adjudication") or {}).get("unresolved") or 0)
        ),
        "reason": (
            "gold-readiness audit passed all sample, coverage, leakage, and "
            "adjudication checks"
            if gold_readiness.get("data_ready")
            else "gold-readiness audit has unresolved release failures"
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
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operational_evidence": evidence,
    }


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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compose_evidence_bundle(
        _load(args.operational_validation),
        _load(args.gold_readiness),
        _load(args.live_shadow) if args.live_shadow else None,
    )
    sources = {
        "operational_validation": args.operational_validation,
        "gold_readiness": args.gold_readiness,
    }
    if args.live_shadow:
        sources["live_shadow"] = args.live_shadow
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


__all__ = ["compose_evidence_bundle"]
