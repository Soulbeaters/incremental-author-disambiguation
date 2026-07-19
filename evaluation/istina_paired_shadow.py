"""Plan and evaluate a privacy-safe, paper-clustered ISTINA shadow comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Mapping, Sequence


@dataclass(frozen=True)
class PairedShadowCriteria:
    absolute_min_mentions: int = 500
    min_unique_papers: int = 100
    min_expected_discordant_rate: float = 0.10
    min_bootstrap_iterations: int = 10_000
    min_randomization_iterations: int = 20_000
    max_bootstrap_iterations: int = 200_000
    max_randomization_iterations: int = 1_000_000
    required_analysis_looks: int = 1


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


def _object(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _hex_identifier(value: Any, length: int) -> bool:
    text = str(value or "").lower()
    return len(text) == length and all(
        character in "0123456789abcdef" for character in text
    )


def required_paired_mentions(
    *,
    alpha: float,
    power: float,
    minimum_absolute_gain: float,
    expected_discordant_rate: float,
) -> int:
    """Normal-approximation sample size for a paired binary difference.

    If p10 and p01 are the two discordant probabilities, the requested gain is
    p10-p01 and the anticipated discordance is p10+p01.  The approximation is
    pre-registration guidance; final inference remains exact/cluster-aware.
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be within (0, 1)")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be within (0, 1)")
    if not 0.0 < minimum_absolute_gain < 1.0:
        raise ValueError("minimum_absolute_gain must be within (0, 1)")
    if not minimum_absolute_gain <= expected_discordant_rate <= 1.0:
        raise ValueError(
            "expected_discordant_rate must be at least the minimum gain and at most 1"
        )
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha / 2.0)
    z_power = normal.inv_cdf(power)
    null_sd = math.sqrt(expected_discordant_rate)
    alternative_sd = math.sqrt(
        max(0.0, expected_discordant_rate - minimum_absolute_gain ** 2)
    )
    numerator = z_alpha * null_sd + z_power * alternative_sd
    return int(math.ceil((numerator / minimum_absolute_gain) ** 2))


def exact_mcnemar_two_sided(runtime_only: int, legacy_only: int) -> float:
    discordant = runtime_only + legacy_only
    if not discordant:
        return 1.0
    tail_limit = min(runtime_only, legacy_only)
    log_probabilities = [
        math.lgamma(discordant + 1)
        - math.lgamma(index + 1)
        - math.lgamma(discordant - index + 1)
        - discordant * math.log(2.0)
        for index in range(tail_limit + 1)
    ]
    maximum = max(log_probabilities)
    tail = math.exp(maximum) * sum(
        math.exp(value - maximum) for value in log_probabilities
    )
    return min(1.0, 2.0 * tail)


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1),
    )
    return ordered[index]


def cluster_sign_flip_p(
    cluster_differences: Sequence[int],
    *,
    iterations: int,
    seed: int,
) -> Dict[str, Any]:
    nonzero = [value for value in cluster_differences if value]
    observed = abs(sum(nonzero))
    if not nonzero:
        return {"p_value": 1.0, "method": "no discordant clusters", "draws": 0}
    if len(nonzero) <= 20:
        extreme = 0
        draws = 1 << len(nonzero)
        for mask in range(draws):
            simulated = sum(
                value if mask & (1 << index) else -value
                for index, value in enumerate(nonzero)
            )
            extreme += abs(simulated) >= observed
        return {
            "p_value": extreme / draws,
            "method": "exact paper-cluster sign flip",
            "draws": draws,
        }
    generator = random.Random(seed)
    extreme = 0
    for _ in range(iterations):
        simulated = sum(
            value if generator.getrandbits(1) else -value
            for value in nonzero
        )
        extreme += abs(simulated) >= observed
    return {
        "p_value": (extreme + 1) / (iterations + 1),
        "method": "deterministic Monte Carlo paper-cluster sign flip",
        "draws": iterations,
    }


def cluster_bootstrap_gain_interval(
    clusters: Sequence[Sequence[tuple[bool, bool]]],
    *,
    iterations: int,
    seed: int,
    alpha: float,
) -> Dict[str, Any]:
    if not clusters:
        return {"lower": None, "upper": None, "iterations": 0}
    generator = random.Random(seed)
    gains = []
    cluster_count = len(clusters)
    for _ in range(iterations):
        total = 0
        difference = 0
        for _sample in range(cluster_count):
            cluster = clusters[generator.randrange(cluster_count)]
            total += len(cluster)
            difference += sum(int(runtime) - int(legacy) for runtime, legacy in cluster)
        gains.append(difference / total if total else 0.0)
    return {
        "lower": _percentile(gains, alpha / 2.0),
        "upper": _percentile(gains, 1.0 - alpha / 2.0),
        "iterations": iterations,
        "method": "paper-cluster percentile bootstrap",
    }


def assess_paired_shadow(
    live_shadow: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    expected_dataset_sha256: str,
    expected_code_revision: str,
    criteria: PairedShadowCriteria | None = None,
) -> Dict[str, Any]:
    criteria = criteria or PairedShadowCriteria()
    document = _object(plan)
    protocol = _object(live_shadow.get("protocol"))
    stats = _object(live_shadow.get("stats"))
    safety = _object(live_shadow.get("safety"))
    release_shadow = _object(
        _object(live_shadow.get("operational_evidence")).get(
            "online_shadow_verified"
        )
    )
    approval = _object(document.get("approval"))
    raw_records = live_shadow.get("records")
    record_collection_valid = isinstance(raw_records, list)
    records = [
        dict(item)
        for item in raw_records or []
        if isinstance(item, Mapping)
    ] if record_collection_valid else []

    expected_dataset_sha256 = str(expected_dataset_sha256 or "").lower()
    expected_code_revision = str(expected_code_revision or "").lower()
    alpha = document.get("alpha")
    power = document.get("power")
    minimum_gain = document.get("minimum_absolute_gain")
    discordant_rate = document.get("expected_discordant_rate")
    min_mentions = document.get("minimum_mentions")
    min_papers = document.get("minimum_unique_papers")
    bootstrap_iterations = document.get("bootstrap_iterations")
    randomization_iterations = document.get("randomization_iterations")
    seed = document.get("random_seed")
    maximum_looks = document.get("maximum_analysis_looks")

    numeric_plan_valid = bool(
        isinstance(alpha, (int, float))
        and not isinstance(alpha, bool)
        and isinstance(power, (int, float))
        and not isinstance(power, bool)
        and isinstance(minimum_gain, (int, float))
        and not isinstance(minimum_gain, bool)
        and isinstance(discordant_rate, (int, float))
        and not isinstance(discordant_rate, bool)
    )
    planned_required_mentions = None
    if numeric_plan_valid:
        try:
            planned_required_mentions = required_paired_mentions(
                alpha=float(alpha),
                power=float(power),
                minimum_absolute_gain=float(minimum_gain),
                expected_discordant_rate=float(discordant_rate),
            )
        except ValueError:
            planned_required_mentions = None
    effective_required_mentions = max(
        criteria.absolute_min_mentions,
        int(min_mentions) if isinstance(min_mentions, int) and not isinstance(min_mentions, bool) else 0,
        planned_required_mentions or 0,
    )

    registered_at = _timestamp(document.get("registered_at"))
    approved_at = _timestamp(approval.get("approved_at"))
    live_generated_at = _timestamp(live_shadow.get("generated_at"))
    plan_checks = [
        _check("plan_schema_version", document.get("schema_version"), 1, document.get("schema_version") == 1, "plan"),
        _check("plan_dataset_sha256", str(document.get("dataset_sha256") or "").lower(), expected_dataset_sha256, bool(expected_dataset_sha256) and str(document.get("dataset_sha256") or "").lower() == expected_dataset_sha256, "plan"),
        _check("plan_code_revision", str(document.get("code_revision") or "").lower(), expected_code_revision, _hex_identifier(expected_code_revision, 40) and str(document.get("code_revision") or "").lower() == expected_code_revision, "plan"),
        _check("primary_endpoint", document.get("primary_endpoint"), "paired known-author top-1 correctness", document.get("primary_endpoint") == "paired known-author top-1 correctness", "plan"),
        _check("two_sided_alpha", alpha, 0.05, alpha == 0.05, "plan"),
        _check("target_power", power, ">=0.8", isinstance(power, (int, float)) and not isinstance(power, bool) and 0.8 <= float(power) < 1.0, "plan"),
        _check("minimum_absolute_gain", minimum_gain, ">=0.02", isinstance(minimum_gain, (int, float)) and not isinstance(minimum_gain, bool) and float(minimum_gain) >= 0.02, "plan"),
        _check("expected_discordant_rate", discordant_rate, f">={criteria.min_expected_discordant_rate} and >= gain", isinstance(discordant_rate, (int, float)) and not isinstance(discordant_rate, bool) and criteria.min_expected_discordant_rate <= float(discordant_rate) <= 1.0 and isinstance(minimum_gain, (int, float)) and float(discordant_rate) >= float(minimum_gain), "plan"),
        _check("minimum_mentions_floor", min_mentions, f">={criteria.absolute_min_mentions}", isinstance(min_mentions, int) and not isinstance(min_mentions, bool) and min_mentions >= criteria.absolute_min_mentions, "plan"),
        _check("minimum_unique_papers", min_papers, f">={criteria.min_unique_papers}", isinstance(min_papers, int) and not isinstance(min_papers, bool) and min_papers >= criteria.min_unique_papers, "plan"),
        _check("bootstrap_iterations", bootstrap_iterations, f"within [{criteria.min_bootstrap_iterations}, {criteria.max_bootstrap_iterations}]", isinstance(bootstrap_iterations, int) and not isinstance(bootstrap_iterations, bool) and criteria.min_bootstrap_iterations <= bootstrap_iterations <= criteria.max_bootstrap_iterations, "plan"),
        _check("randomization_iterations", randomization_iterations, f"within [{criteria.min_randomization_iterations}, {criteria.max_randomization_iterations}]", isinstance(randomization_iterations, int) and not isinstance(randomization_iterations, bool) and criteria.min_randomization_iterations <= randomization_iterations <= criteria.max_randomization_iterations, "plan"),
        _check("random_seed", seed, "non-negative integer", isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0, "plan"),
        _check("single_analysis_look", maximum_looks, criteria.required_analysis_looks, maximum_looks == criteria.required_analysis_looks, "plan"),
        _check("registration_timestamp", document.get("registered_at"), "timezone-aware and no later than approval/live run", registered_at is not None and approved_at is not None and live_generated_at is not None and registered_at <= approved_at <= live_generated_at, "plan"),
        _check("registration_references", [document.get("registration_reference"), approval.get("reference")], "two non-empty references", bool(str(document.get("registration_reference") or "").strip()) and bool(str(approval.get("reference") or "").strip()), "plan"),
        _check("power_calculation", planned_required_mentions, "valid paired design", planned_required_mentions is not None, "power"),
    ]

    clusters_by_paper: Dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    identities = set()
    record_format_valid = True
    for record in records:
        paper = str(record.get("article_id_hash") or "")
        position = str(record.get("position") or "")
        runtime_correct = record.get("runtime_correct")
        legacy_correct = record.get("legacy_correct")
        identity = (paper, position)
        if (
            not paper
            or not position
            or identity in identities
            or type(runtime_correct) is not bool
            or type(legacy_correct) is not bool
            or record.get("legacy_result_present") is not True
            or bool(record.get("error"))
            or bool(record.get("service_error"))
        ):
            record_format_valid = False
            continue
        identities.add(identity)
        clusters_by_paper[paper].append((runtime_correct, legacy_correct))

    table = {
        "both_correct": 0,
        "runtime_only_correct": 0,
        "legacy_only_correct": 0,
        "both_incorrect": 0,
    }
    for cluster in clusters_by_paper.values():
        for runtime_correct, legacy_correct in cluster:
            cell = (
                "both_correct" if runtime_correct and legacy_correct else
                "runtime_only_correct" if runtime_correct else
                "legacy_only_correct" if legacy_correct else
                "both_incorrect"
            )
            table[cell] += 1
    n = sum(table.values())
    paper_count = len(clusters_by_paper)
    runtime_correct_count = table["both_correct"] + table["runtime_only_correct"]
    legacy_correct_count = table["both_correct"] + table["legacy_only_correct"]
    gain = (runtime_correct_count - legacy_correct_count) / n if n else None
    mcnemar_p = exact_mcnemar_two_sided(
        table["runtime_only_correct"], table["legacy_only_correct"]
    ) if n else None
    cluster_differences = [
        sum(int(runtime) - int(legacy) for runtime, legacy in cluster)
        for cluster in clusters_by_paper.values()
    ]
    safe_randomization_iterations = (
        randomization_iterations
        if isinstance(randomization_iterations, int)
        and not isinstance(randomization_iterations, bool)
        and 1 <= randomization_iterations <= criteria.max_randomization_iterations
        else 1
    )
    safe_bootstrap_iterations = (
        bootstrap_iterations
        if isinstance(bootstrap_iterations, int)
        and not isinstance(bootstrap_iterations, bool)
        and 1 <= bootstrap_iterations <= criteria.max_bootstrap_iterations
        else 1
    )
    randomization = cluster_sign_flip_p(
        cluster_differences,
        iterations=safe_randomization_iterations,
        seed=(seed if isinstance(seed, int) and not isinstance(seed, bool) else 0),
    )
    confidence_interval = cluster_bootstrap_gain_interval(
        list(clusters_by_paper.values()),
        iterations=safe_bootstrap_iterations,
        seed=((seed + 1) if isinstance(seed, int) and not isinstance(seed, bool) else 1),
        alpha=(float(alpha) if isinstance(alpha, (int, float)) and 0.0 < float(alpha) < 1.0 else 0.05),
    )

    analysis_checks = [
        _check("live_schema_version", live_shadow.get("schema_version"), 1, live_shadow.get("schema_version") == 1, "input"),
        _check("live_dataset_sha256", str(protocol.get("dataset_sha256") or "").lower(), expected_dataset_sha256, str(protocol.get("dataset_sha256") or "").lower() == expected_dataset_sha256, "input"),
        _check("live_code_revision", str(protocol.get("code_revision") or "").lower(), expected_code_revision, _hex_identifier(expected_code_revision, 40) and str(protocol.get("code_revision") or "").lower() == expected_code_revision, "input"),
        _check("live_shadow_mode", protocol.get("mode"), "shadow", protocol.get("mode") == "shadow", "input"),
        _check("zero_write_calls", [protocol.get("write_calls"), stats.get("authorized_commands")], [0, 0], protocol.get("write_calls") == 0 and stats.get("authorized_commands") == 0, "safety"),
        _check("no_write_authorized", safety.get("no_write_authorized"), True, safety.get("no_write_authorized") is True, "safety"),
        _check("zero_service_errors", stats.get("service_errors"), 0, stats.get("service_errors") == 0, "fairness"),
        _check("release_shadow_verified", release_shadow.get("verified"), True, release_shadow.get("verified") is True, "input"),
        _check("records_complete", len(records), stats.get("attempted_mentions"), record_collection_valid and len(records) == stats.get("attempted_mentions") == stats.get("runtime_decisions") == stats.get("service_successful_mentions") == stats.get("legacy_result_present"), "input"),
        _check("record_format_and_uniqueness", record_collection_valid and record_format_valid and len(identities) == len(records), True, record_collection_valid and record_format_valid and len(identities) == len(records), "input"),
        _check("powered_mentions", n, f">={effective_required_mentions}", n >= effective_required_mentions, "power"),
        _check("unique_papers", paper_count, f">={min_papers}", isinstance(min_papers, int) and paper_count >= min_papers, "power"),
        _check("minimum_absolute_gain_observed", gain, f">={minimum_gain}", gain is not None and isinstance(minimum_gain, (int, float)) and gain >= float(minimum_gain), "effect"),
        _check("mcnemar_significance", mcnemar_p, f"<={alpha}", mcnemar_p is not None and isinstance(alpha, (int, float)) and mcnemar_p <= float(alpha), "inference"),
        _check("paper_cluster_significance", randomization.get("p_value"), f"<={alpha}", isinstance(alpha, (int, float)) and randomization.get("p_value") <= float(alpha), "inference"),
        _check("paper_cluster_interval", confidence_interval.get("lower"), ">0", confidence_interval.get("lower") is not None and confidence_interval.get("lower") > 0.0, "inference"),
    ]
    checks = plan_checks + analysis_checks
    failures = [item for item in checks if not item["passed"]]
    cluster_sizes = [len(cluster) for cluster in clusters_by_paper.values()]
    return {
        "schema_version": 1,
        "verified": not failures,
        "criteria": asdict(criteria),
        "power_plan": {
            "planned_required_mentions": planned_required_mentions,
            "effective_required_mentions": effective_required_mentions,
            "minimum_unique_papers": min_papers,
            "alpha": alpha,
            "power": power,
            "minimum_absolute_gain": minimum_gain,
            "expected_discordant_rate": discordant_rate,
        },
        "population": {
            "paired_mentions": n,
            "unique_papers": paper_count,
            "cluster_size_min": min(cluster_sizes) if cluster_sizes else None,
            "cluster_size_max": max(cluster_sizes) if cluster_sizes else None,
            "cluster_size_mean": sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else None,
        },
        "paired_table": table,
        "runtime_correct": runtime_correct_count,
        "legacy_correct": legacy_correct_count,
        "runtime_accuracy": runtime_correct_count / n if n else None,
        "legacy_accuracy": legacy_correct_count / n if n else None,
        "absolute_gain": gain,
        "mcnemar_exact_two_sided_p": mcnemar_p,
        "cluster_randomization": randomization,
        "cluster_bootstrap_gain_interval": confidence_interval,
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "failures": failures,
        "privacy": {
            "mention_level_records_emitted": False,
            "raw_names_emitted": False,
            "raw_identity_ids_emitted": False,
        },
        "operational_evidence": {
            "paired_shadow_analysis_verified": {
                "verified": not failures,
                "paired_mentions": n,
                "unique_papers": paper_count,
                "required_mentions": effective_required_mentions,
                "absolute_gain": gain,
                "mcnemar_p": mcnemar_p,
                "cluster_p": randomization.get("p_value"),
                "cluster_interval_lower": confidence_interval.get("lower"),
            }
        },
    }


def _load(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-shadow", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-dataset", type=Path, required=True)
    parser.add_argument("--expected-code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess_paired_shadow(
        _load(args.live_shadow),
        _load(args.plan),
        expected_dataset_sha256=sha256_file(args.expected_dataset),
        expected_code_revision=args.expected_code_revision,
    )
    result["inputs"] = {
        "live_shadow": {"name": args.live_shadow.name, "sha256": sha256_file(args.live_shadow)},
        "plan": {"name": args.plan.name, "sha256": sha256_file(args.plan)},
        "dataset": {"name": args.expected_dataset.name, "sha256": sha256_file(args.expected_dataset)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "verified": result["verified"],
        "paired_mentions": result["population"]["paired_mentions"],
        "required_mentions": result["power_plan"]["effective_required_mentions"],
        "unique_papers": result["population"]["unique_papers"],
        "absolute_gain": result["absolute_gain"],
        "mcnemar_p": result["mcnemar_exact_two_sided_p"],
        "cluster_p": result["cluster_randomization"]["p_value"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = [
    "PairedShadowCriteria",
    "assess_paired_shadow",
    "cluster_bootstrap_gain_interval",
    "cluster_sign_flip_p",
    "exact_mcnemar_two_sided",
    "required_paired_mentions",
]
