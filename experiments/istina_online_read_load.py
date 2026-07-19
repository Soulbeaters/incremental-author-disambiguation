"""Run an explicitly approved, rate-limited, read-only ISTINA load test.

This tool calls only the existing candidate lookup endpoint.  It contains no
write adapter and emits aggregate, dataset-hash-bound evidence.  The operator
must supply an approval reference and an explicit acknowledgement flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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
from experiments.istina_export_temporal_evaluation import load_articles
from integrations.istina_disambiguation_client import (
    DEFAULT_ISTINA_DISAMBIGUATION_URL,
    IstinaDisambiguationClient,
)
from integrations.istina_export_quality import deduplicate_exact_author_rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if args.requests < 1:
        raise ValueError("requests must be positive")
    if re.fullmatch(r"[0-9a-fA-F]{40}", args.code_revision) is None:
        raise ValueError("code-revision must be a full 40-hex Git commit")

    raw_articles = load_articles(args.dataset)
    articles, duplicate_rows_removed = deduplicate_exact_author_rows(raw_articles)
    client = IstinaDisambiguationClient(
        service_url=args.service_url,
        timeout=args.service_timeout,
    )

    def request(article: Mapping[str, Any]) -> Any:
        authors = [
            client.from_exported_author(dict(author))
            for author in article.get("authors") or []
        ]
        return client.request_candidates(authors, args.man_id)

    load = run_read_only_load(
        articles,
        request_count=args.requests,
        concurrency=args.concurrency,
        max_rps=args.max_rps,
        request_func=request,
    )
    criteria = DeploymentCriteria()
    verified = bool(
        load["requests"] >= criteria.min_online_load_requests
        and load["error_rate"] <= criteria.max_online_load_error_rate
        and load["latency_ms_p95"] is not None
        and load["latency_ms_p95"] <= criteria.max_online_load_p95_latency_ms
    )
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "source_system": "istina",
            "mode": "read_only_candidate_lookup",
            "dataset_name": args.dataset.name,
            "dataset_sha256": sha256_file(args.dataset),
            "code_revision": args.code_revision.lower(),
            "service_url_sha256": hashlib.sha256(
                args.service_url.encode("utf-8")
            ).hexdigest(),
            "requests": args.requests,
            "concurrency": args.concurrency,
            "max_rps": args.max_rps,
            "service_timeout_seconds": args.service_timeout,
            "exact_duplicate_author_rows_removed": duplicate_rows_removed,
            "approved_change_reference": args.approved_change_reference,
        },
        "stats": {
            "requests": load["requests"],
            "completed": load["completed"],
            "errors": load["errors"],
            "write_calls": 0,
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
            "criteria": {
                "min_requests": criteria.min_online_load_requests,
                "max_error_rate": criteria.max_online_load_error_rate,
                "max_p95_latency_ms": criteria.max_online_load_p95_latency_ms,
            },
        },
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
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = ["StartRateLimiter", "percentile", "run_read_only_load"]
