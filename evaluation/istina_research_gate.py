"""Separate research readiness from an ISTINA production release decision.

Passing this gate never authorizes writes. It reports whether the framework is
ready for reproducible research and, separately, whether a preregistered paired
study supports a superiority claim over the incumbent ISTINA service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

try:
    from evaluation.istina_paired_shadow import exact_mcnemar_two_sided
except ModuleNotFoundError:  # Support ``python evaluation/...py`` from repo root.
    from istina_paired_shadow import exact_mcnemar_two_sided


@dataclass(frozen=True)
class ResearchCriteria:
    min_performance_trials: int = 3
    min_paired_mentions: int = 1_960
    min_unique_papers: int = 100
    min_absolute_gain: float = 0.02
    max_p_value: float = 0.05


def _object(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _diagnostic_comparison(live: Mapping[str, Any]) -> Dict[str, Any]:
    records = live.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        records = []
    valid = [
        record
        for record in records
        if isinstance(record, Mapping)
        and type(record.get("runtime_correct")) is bool
        and type(record.get("legacy_correct")) is bool
    ]
    runtime_only = sum(
        record["runtime_correct"] and not record["legacy_correct"]
        for record in valid
    )
    legacy_only = sum(
        record["legacy_correct"] and not record["runtime_correct"]
        for record in valid
    )
    papers = {
        record.get("article_id_hash")
        for record in valid
        if record.get("article_id_hash")
    }
    count = len(valid)
    gain = (runtime_only - legacy_only) / count if count else None
    return {
        "verified": False,
        "population": {
            "paired_mentions": count,
            "unique_papers": len(papers),
        },
        "absolute_gain": gain,
        "mcnemar_exact_two_sided_p": (
            exact_mcnemar_two_sided(runtime_only, legacy_only)
            if count
            else None
        ),
        "cluster_randomization": {"p_value": None},
        "cluster_bootstrap_gain_interval": {"lower": None},
        "power_plan": {},
        "source": "unregistered live diagnostic",
    }


def assess_research_readiness(
    temporal_replay: Mapping[str, Any],
    gold_readiness: Mapping[str, Any],
    live_diagnostic: Mapping[str, Any],
    performance: Mapping[str, Any],
    paper_package: Mapping[str, Any],
    paired_analysis: Optional[Mapping[str, Any]] = None,
    criteria: Optional[ResearchCriteria] = None,
) -> Dict[str, Any]:
    criteria = criteria or ResearchCriteria()
    temporal_protocol = _object(temporal_replay.get("protocol"))
    production_split = _object(gold_readiness.get("production_temporal_split"))
    provenance = _object(gold_readiness.get("provenance"))
    adjudication = _object(gold_readiness.get("adjudication"))
    live_protocol = _object(live_diagnostic.get("protocol"))
    live_stats = _object(live_diagnostic.get("stats"))
    live_safety = _object(live_diagnostic.get("safety"))
    performance_summary = _object(performance.get("summary"))
    integrity = _object(paper_package.get("integrity"))

    dataset_hashes = {
        str(value).lower()
        for value in (
            temporal_protocol.get("dataset_sha256"),
            live_protocol.get("dataset_sha256"),
        )
        if value
    }
    quality_rows = paper_package.get("quality_table")
    quality_rows = quality_rows if isinstance(quality_rows, list) else []
    public_sources = {
        str(row.get("source") or "")
        for row in quality_rows
        if isinstance(row, Mapping)
    }
    public_validation_present = (
        any(source.startswith("openalex") for source in public_sources)
        and any(source.startswith("aminer") for source in public_sources)
    )

    framework_checks = [
        _check(
            "strict_temporal_split",
            temporal_protocol.get("split_strategy"),
            "temporal",
            temporal_protocol.get("split_strategy") == "temporal",
            "protocol",
        ),
        _check(
            "zero_paper_overlap",
            production_split.get("paper_overlap"),
            0,
            production_split.get("paper_overlap") == 0,
            "leakage",
        ),
        _check(
            "exact_duplicate_cleaning",
            temporal_protocol.get("exact_duplicate_cleaning_applied"),
            True,
            temporal_protocol.get("exact_duplicate_cleaning_applied") is True,
            "data",
        ),
        _check(
            "single_dataset_identity",
            sorted(dataset_hashes),
            "one shared non-empty SHA-256",
            len(dataset_hashes) == 1
            and len(next(iter(dataset_hashes), "")) == 64,
            "binding",
        ),
        _check(
            "legacy_comparator_independence",
            {
                "temporal_fallback": temporal_protocol.get(
                    "framework_legacy_fallback_enabled"
                ),
                "temporal_observation_only": temporal_protocol.get(
                    "legacy_service_observation_only"
                ),
                "live_fallback": live_protocol.get(
                    "framework_legacy_fallback_enabled"
                ),
                "live_observation_only": live_protocol.get(
                    "legacy_service_observation_only"
                ),
            },
            "fallback=false and observation_only=true for both arms",
            temporal_protocol.get("framework_legacy_fallback_enabled") is False
            and temporal_protocol.get("legacy_service_observation_only") is True
            and live_protocol.get("framework_legacy_fallback_enabled") is False
            and live_protocol.get("legacy_service_observation_only") is True,
            "fairness",
        ),
        _check(
            "zero_write_diagnostic",
            {
                "write_calls": live_protocol.get("write_calls"),
                "authorized_commands": live_stats.get("authorized_commands"),
                "no_write_authorized": live_safety.get("no_write_authorized"),
            },
            {
                "write_calls": 0,
                "authorized_commands": 0,
                "no_write_authorized": True,
            },
            live_protocol.get("write_calls") == 0
            and live_stats.get("authorized_commands") == 0
            and live_safety.get("no_write_authorized") is True,
            "safety",
        ),
        _check(
            "paper_package_integrity",
            {
                "verified": integrity.get("verified"),
                "failed": _object(integrity.get("summary")).get("failed"),
            },
            {"verified": True, "failed": 0},
            integrity.get("verified") is True
            and _object(integrity.get("summary")).get("failed") == 0,
            "reproducibility",
        ),
        _check(
            "offline_performance_repeatability",
            {
                "verified": performance_summary.get("verified"),
                "trials": performance_summary.get("trial_count"),
            },
            {
                "verified": True,
                "trials": f">={criteria.min_performance_trials}",
            },
            performance_summary.get("verified") is True
            and int(performance_summary.get("trial_count") or 0)
            >= criteria.min_performance_trials,
            "reproducibility",
        ),
        _check(
            "public_transfer_validation",
            sorted(public_sources),
            "current-runtime OpenAlex and AMiner rows",
            public_validation_present,
            "external_validation",
        ),
    ]

    analysis = (
        dict(paired_analysis)
        if isinstance(paired_analysis, Mapping)
        else _diagnostic_comparison(live_diagnostic)
    )
    population = _object(analysis.get("population"))
    power_plan = _object(analysis.get("power_plan"))
    randomization = _object(analysis.get("cluster_randomization"))
    interval = _object(analysis.get("cluster_bootstrap_gain_interval"))
    paired_mentions = int(population.get("paired_mentions") or 0)
    unique_papers = int(population.get("unique_papers") or 0)
    planned_mentions = int(power_plan.get("effective_required_mentions") or 0)
    required_mentions = max(criteria.min_paired_mentions, planned_mentions)
    gain = analysis.get("absolute_gain")
    mcnemar_p = analysis.get("mcnemar_exact_two_sided_p")
    cluster_p = randomization.get("p_value")
    interval_lower = interval.get("lower")

    claim_checks = [
        _check(
            "independently_verified_provenance",
            provenance.get("verified"),
            True,
            provenance.get("verified") is True,
            "labels",
        ),
        _check(
            "resolved_label_conflicts",
            adjudication.get("unresolved"),
            0,
            adjudication.get("unresolved") == 0,
            "labels",
        ),
        _check(
            "preregistered_paired_analysis",
            analysis.get("verified"),
            True,
            analysis.get("verified") is True,
            "design",
        ),
        _check(
            "powered_paired_mentions",
            paired_mentions,
            f">={required_mentions}",
            paired_mentions >= required_mentions,
            "power",
        ),
        _check(
            "paired_unique_papers",
            unique_papers,
            f">={criteria.min_unique_papers}",
            unique_papers >= criteria.min_unique_papers,
            "power",
        ),
        _check(
            "minimum_absolute_gain",
            gain,
            f">={criteria.min_absolute_gain}",
            isinstance(gain, (int, float))
            and not isinstance(gain, bool)
            and gain >= criteria.min_absolute_gain,
            "effect",
        ),
        _check(
            "mcnemar_significance",
            mcnemar_p,
            f"<={criteria.max_p_value}",
            isinstance(mcnemar_p, (int, float))
            and not isinstance(mcnemar_p, bool)
            and mcnemar_p <= criteria.max_p_value,
            "inference",
        ),
        _check(
            "paper_cluster_significance",
            cluster_p,
            f"<={criteria.max_p_value}",
            isinstance(cluster_p, (int, float))
            and not isinstance(cluster_p, bool)
            and cluster_p <= criteria.max_p_value,
            "inference",
        ),
        _check(
            "paper_cluster_interval",
            interval_lower,
            ">0",
            isinstance(interval_lower, (int, float))
            and not isinstance(interval_lower, bool)
            and interval_lower > 0.0,
            "inference",
        ),
    ]

    framework_failures = [item for item in framework_checks if not item["passed"]]
    claim_failures = [item for item in claim_checks if not item["passed"]]
    return {
        "schema_version": 1,
        "framework_ready": not framework_failures,
        "superiority_claim_ready": not claim_failures,
        "writes_authorized": False,
        "scope": (
            "Research and ISTINA integration evidence only; this result is "
            "not a production release authorization."
        ),
        "criteria": asdict(criteria),
        "framework": {
            "summary": {
                "passed": len(framework_checks) - len(framework_failures),
                "failed": len(framework_failures),
                "total": len(framework_checks),
            },
            "checks": framework_checks,
            "failures": framework_failures,
        },
        "superiority_claim": {
            "comparison_source": analysis.get("source", "paired analysis"),
            "summary": {
                "passed": len(claim_checks) - len(claim_failures),
                "failed": len(claim_failures),
                "total": len(claim_checks),
            },
            "checks": claim_checks,
            "failures": claim_failures,
        },
    }


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return dict(document)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal-replay", type=Path, required=True)
    parser.add_argument("--gold-readiness", type=Path, required=True)
    parser.add_argument("--live-diagnostic", type=Path, required=True)
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--paper-package", type=Path, required=True)
    parser.add_argument("--paired-analysis", type=Path)
    parser.add_argument("--criteria", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    criteria = ResearchCriteria(**(_load(args.criteria) if args.criteria else {}))
    result = assess_research_readiness(
        _load(args.temporal_replay),
        _load(args.gold_readiness),
        _load(args.live_diagnostic),
        _load(args.performance),
        _load(args.paper_package),
        _load(args.paired_analysis) if args.paired_analysis else None,
        criteria,
    )
    source_paths = {
        "temporal_replay": args.temporal_replay,
        "gold_readiness": args.gold_readiness,
        "live_diagnostic": args.live_diagnostic,
        "performance": args.performance,
        "paper_package": args.paper_package,
    }
    if args.paired_analysis:
        source_paths["paired_analysis"] = args.paired_analysis
    result["inputs"] = {
        name: {"name": path.name, "sha256": _sha256_file(path)}
        for name, path in source_paths.items()
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


__all__ = ["ResearchCriteria", "assess_research_readiness"]
