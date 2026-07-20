"""Run an explicitly approved, rate-limited, read-only ISTINA load test.

This tool calls only the existing candidate lookup endpoint.  It contains no
write adapter and emits aggregate, dataset-hash-bound evidence.  The operator
must supply an approval reference and an explicit acknowledgement flag.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.istina_deployment_evidence import DeploymentCriteria
from evaluation.istina_online_load_plan import (
    INSTITUTIONAL_LOAD_SCOPE,
    assess_online_load_plan,
    man_id_sha256,
    sha256_file,
    sha256_text,
)
from evaluation.istina_revision_binding import require_current_git_revision
from experiments.istina_export_temporal_evaluation import load_articles
from integrations.istina_disambiguation_client import (
    DEFAULT_ISTINA_DISAMBIGUATION_URL,
    IstinaDisambiguationClient,
)
from integrations.istina_export_quality import deduplicate_exact_author_rows


USER_CANARY_SCOPE = "user_authorized_canary"
MAX_USER_CANARY_REQUESTS = 20


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


class StartRateLimiter:
    def __init__(self, max_rps: float) -> None:
        self.interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self.next_start = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_start - now)
            self.next_start = max(now, self.next_start) + self.interval
        if delay:
            time.sleep(delay)


def run_read_only_load(
    articles: Sequence[Mapping[str, Any]],
    *,
    request_count: int,
    concurrency: int,
    max_rps: float,
    request_func: Callable[[Mapping[str, Any]], Any],
) -> Dict[str, Any]:
    eligible = [article for article in articles if article.get("authors")]
    if not eligible:
        raise ValueError("dataset has no articles with authors")
    if request_count < 1:
        raise ValueError("request_count must be positive")
    if not 1 <= concurrency <= 16:
        raise ValueError("concurrency must be within [1, 16]")
    limiter = StartRateLimiter(max_rps)

    def invoke(index: int) -> tuple[bool, float]:
        article = eligible[index % len(eligible)]
        limiter.wait()
        started = time.perf_counter()
        try:
            request_func(article)
            success = True
        except Exception:
            success = False
        return success, (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        outcomes = list(executor.map(invoke, range(request_count)))
    elapsed = time.perf_counter() - started
    latencies = [latency for _success, latency in outcomes]
    errors = sum(not success for success, _latency in outcomes)
    return {
        "requests": request_count,
        "completed": len(outcomes),
        "errors": errors,
        "error_rate": errors / request_count,
        "elapsed_seconds": elapsed,
        "throughput_requests_per_second": request_count / elapsed if elapsed else None,
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
        "latency_ms_p99": percentile(latencies, 0.99),
        "latency_ms_max": max(latencies) if latencies else None,
    }


def assess_load_evidence(
    load: Mapping[str, Any],
    *,
    approval_scope: str,
    load_plan_verified: bool = False,
    requests_outside_approved_window: int = 0,
    criteria: DeploymentCriteria | None = None,
) -> Dict[str, Any]:
    criteria = criteria or DeploymentCriteria()
    requests = load.get("requests")
    error_rate = load.get("error_rate")
    latency_p95 = load.get("latency_ms_p95")
    threshold_passed = bool(
        not isinstance(requests, bool)
        and isinstance(requests, int)
        and requests >= criteria.min_online_load_requests
        and not isinstance(error_rate, bool)
        and isinstance(error_rate, (int, float))
        and math.isfinite(float(error_rate))
        and 0.0 <= float(error_rate) <= criteria.max_online_load_error_rate
        and not isinstance(latency_p95, bool)
        and isinstance(latency_p95, (int, float))
        and math.isfinite(float(latency_p95))
        and 0.0 <= float(latency_p95)
        <= criteria.max_online_load_p95_latency_ms
    )
    institutional_approval = bool(
        approval_scope == INSTITUTIONAL_LOAD_SCOPE
        and load_plan_verified
        and requests_outside_approved_window == 0
    )
    return {
        "verified": threshold_passed and institutional_approval,
        "threshold_passed": threshold_passed,
        "institutional_approval": institutional_approval,
        "evidence_classification": (
            "release_scale_online_load"
            if threshold_passed and institutional_approval
            else (
                "unverified_institutional_load"
                if approval_scope == INSTITUTIONAL_LOAD_SCOPE
                else "bounded_non_release_canary"
            )
        ),
    }


def validate_load_approval_scope(
    request_count: int,
    approval_scope: str,
    *,
    load_plan_supplied: bool = False,
) -> None:
    if approval_scope not in {INSTITUTIONAL_LOAD_SCOPE, USER_CANARY_SCOPE}:
        raise ValueError("unknown online-load approval scope")
    if approval_scope == USER_CANARY_SCOPE and request_count > MAX_USER_CANARY_REQUESTS:
        raise ValueError(
            f"user-authorized canary is capped at {MAX_USER_CANARY_REQUESTS} requests"
        )
    if approval_scope == USER_CANARY_SCOPE and load_plan_supplied:
        raise ValueError("user-authorized canary must not use an institutional load plan")
    if approval_scope == INSTITUTIONAL_LOAD_SCOPE and not load_plan_supplied:
        raise ValueError("institutional load requires --load-plan")


def _load_json_object(path: Path) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return dict(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=1_000)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-rps", type=float, default=2.0)
    parser.add_argument("--man-id", type=int, required=True)
    parser.add_argument("--service-url", default=DEFAULT_ISTINA_DISAMBIGUATION_URL)
    parser.add_argument("--service-timeout", type=float, default=30.0)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--approved-change-reference", required=True)
    parser.add_argument(
        "--load-plan",
        type=Path,
        help="Required immutable approval plan for institutional load only.",
    )
    parser.add_argument(
        "--approval-scope",
        choices=[INSTITUTIONAL_LOAD_SCOPE, USER_CANARY_SCOPE],
        required=True,
        help=(
            "Institutional release evidence requires an approved load window; "
            "a user-authorized canary is capped and can never verify release."
        ),
    )
    parser.add_argument("--acknowledge-read-only-load", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.acknowledge_read_only_load:
        raise ValueError("--acknowledge-read-only-load is required")
    if not str(args.approved_change_reference).strip():
        raise ValueError("approved change reference must be non-empty")
    if not 1 <= args.concurrency <= 16:
        raise ValueError("concurrency must be within [1, 16]")
    if not 0.1 <= args.max_rps <= 20.0:
        raise ValueError("max-rps must be within [0.1, 20]")
    if not 0.1 <= args.service_timeout <= 120.0:
        raise ValueError("service-timeout must be within [0.1, 120]")
    if args.requests < 1:
        raise ValueError("requests must be positive")
    validate_load_approval_scope(
        args.requests,
        args.approval_scope,
        load_plan_supplied=args.load_plan is not None,
    )
    observed_code_revision = require_current_git_revision(
        args.code_revision,
        PROJECT_ROOT,
    )

    dataset_sha256 = sha256_file(args.dataset)
    load_plan_sha256 = None
    load_plan_validation: Dict[str, Any] | None = None
    approved_window_end: datetime | None = None
    if args.load_plan is not None:
        load_plan_sha256 = sha256_file(args.load_plan)
        load_plan_validation = assess_online_load_plan(
            _load_json_object(args.load_plan),
            expected_dataset_sha256=dataset_sha256,
            expected_code_revision=observed_code_revision,
            expected_service_url_sha256=sha256_text(args.service_url),
            expected_man_id_sha256=man_id_sha256(args.man_id),
            expected_requests=args.requests,
            expected_concurrency=args.concurrency,
            expected_max_rps=args.max_rps,
            expected_service_timeout_seconds=args.service_timeout,
            expected_change_reference=args.approved_change_reference,
            require_active_window=True,
        )
        if not load_plan_validation["verified"]:
            failed = ", ".join(
                item["name"] for item in load_plan_validation["failures"]
            )
            raise ValueError(f"online load plan validation failed: {failed}")
        approved_window_end = datetime.fromisoformat(
            load_plan_validation["approved_window"]["end"]
        )

    raw_articles = load_articles(args.dataset)
    articles, duplicate_rows_removed = deduplicate_exact_author_rows(raw_articles)
    client = IstinaDisambiguationClient(
        service_url=args.service_url,
        timeout=args.service_timeout,
    )

    window_guard_failures = 0
    window_guard_lock = threading.Lock()

    def request(article: Mapping[str, Any]) -> Any:
        nonlocal window_guard_failures
        if (
            approved_window_end is not None
            and datetime.now(timezone.utc) > approved_window_end
        ):
            with window_guard_lock:
                window_guard_failures += 1
            raise RuntimeError("approved online-load window ended before request start")
        authors = [
            client.from_exported_author(dict(author))
            for author in article.get("authors") or []
        ]
        return client.request_candidates(authors, args.man_id)

    execution_started_at = datetime.now(timezone.utc)
    load = run_read_only_load(
        articles,
        request_count=args.requests,
        concurrency=args.concurrency,
        max_rps=args.max_rps,
        request_func=request,
    )
    criteria = DeploymentCriteria()
    assessment = assess_load_evidence(
        load,
        approval_scope=args.approval_scope,
        load_plan_verified=bool(
            load_plan_validation and load_plan_validation["verified"]
        ),
        requests_outside_approved_window=window_guard_failures,
        criteria=criteria,
    )
    verified = assessment["verified"]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "source_system": "istina",
            "mode": "read_only_candidate_lookup",
            "dataset_name": args.dataset.name,
            "dataset_sha256": dataset_sha256,
            "code_revision": observed_code_revision,
            "repository_head_verified": True,
            "service_url_sha256": sha256_text(args.service_url),
            "man_id_sha256": man_id_sha256(args.man_id),
            "requests": args.requests,
            "concurrency": args.concurrency,
            "max_rps": args.max_rps,
            "service_timeout_seconds": args.service_timeout,
            "exact_duplicate_author_rows_removed": duplicate_rows_removed,
            "approved_change_reference": args.approved_change_reference,
            "approval_scope": args.approval_scope,
            "execution_started_at": execution_started_at.isoformat(),
            "online_load_plan_name": args.load_plan.name if args.load_plan else None,
            "online_load_plan_sha256": load_plan_sha256,
        },
        "stats": {
            "requests": load["requests"],
            "completed": load["completed"],
            "errors": load["errors"],
            "write_calls": 0,
            "requests_outside_approved_window": window_guard_failures,
        },
        "metrics": {
            key: value for key, value in load.items()
            if key not in {"requests", "completed", "errors"}
        },
        "safety": {
            "verified": verified,
            "write_client_present": False,
            "write_calls": 0,
            "explicit_operator_acknowledgement": True,
            "threshold_passed": assessment["threshold_passed"],
            "institutional_approval": assessment["institutional_approval"],
            "load_plan_verified": bool(
                load_plan_validation and load_plan_validation["verified"]
            ),
            "repository_head_verified": True,
            "evidence_classification": assessment[
                "evidence_classification"
            ],
            "criteria": {
                "min_requests": criteria.min_online_load_requests,
                "max_error_rate": criteria.max_online_load_error_rate,
                "max_p95_latency_ms": criteria.max_online_load_p95_latency_ms,
            },
        },
    }
    if load_plan_validation is not None:
        result["load_plan_validation"] = {
            "verified": load_plan_validation["verified"],
            "summary": load_plan_validation["summary"],
            "approved_window": load_plan_validation["approved_window"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "verified": verified,
        "requests": load["requests"],
        "errors": load["errors"],
        "error_rate": load["error_rate"],
        "p95_latency_ms": load["latency_ms_p95"],
        "write_calls": 0,
        "evidence_classification": assessment["evidence_classification"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = [
    "INSTITUTIONAL_LOAD_SCOPE",
    "MAX_USER_CANARY_REQUESTS",
    "USER_CANARY_SCOPE",
    "StartRateLimiter",
    "assess_load_evidence",
    "percentile",
    "run_read_only_load",
    "sha256_file",
    "validate_load_approval_scope",
]
