"""Run a bounded, no-write live shadow through the production safety runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.decision_types import Decision  # noqa: E402
from experiments.istina_export_temporal_evaluation import (  # noqa: E402
    article_id,
    iter_mentions,
    load_articles,
    split_mentions,
)
from experiments.istina_runtime_replay import percentile  # noqa: E402
from integrations.istina_disambiguation_client import (  # noqa: E402
    DEFAULT_ISTINA_DISAMBIGUATION_URL,
    IstinaDisambiguationClient,
)
from integrations.istina_pipeline import (  # noqa: E402
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
    article_mentions,
)
from integrations.istina_export_quality import (  # noqa: E402
    deduplicate_exact_author_rows,
)
from integrations.istina_production_runtime import (  # noqa: E402
    CircuitBreaker,
    CircuitBreakerConfig,
    IstinaProductionRuntime,
    RuntimeMode,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_identifier(value: Any, salt: str) -> str:
    return hashlib.sha256(f"{value}|{salt}".encode("utf-8")).hexdigest()[:16]


def release_shadow_is_verified(
    smoke_verified: bool,
    mentions: int,
    minimum_mentions: int = 500,
) -> bool:
    """Require both a healthy smoke and release-scale online volume."""

    return bool(smoke_verified and mentions >= minimum_mentions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--man-id", type=int, default=4705445)
    parser.add_argument("--service-url", default=DEFAULT_ISTINA_DISAMBIGUATION_URL)
    parser.add_argument("--service-timeout", type=float, default=20.0)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument(
        "--split-strategy",
        choices=["temporal", "per-author-holdout"],
        default="temporal",
    )
    parser.add_argument("--train-through-year", type=int, default=2023)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit < 1:
        raise ValueError("limit must be positive")

    raw_articles = load_articles(args.dataset)
    raw_mentions = sum(
        len(article.get("authors") or []) for article in raw_articles
    )
    articles, exact_duplicates_removed = deduplicate_exact_author_rows(
        raw_articles
    )
    mentions = list(iter_mentions(articles))
    history, test = split_mentions(
        mentions,
        args.split_strategy,
        args.train_through_year,
    )
    client = IstinaDisambiguationClient(
        service_url=args.service_url,
        timeout=args.service_timeout,
    )
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=IstinaPipelineConfig(
            use_remote_fallback=True,
            enable_calibrated_candidate_rescue=False,
            run_id="istina-live-shadow",
        ),
        service_client=client,
    )
    known_ids = set(pipeline.history_state.external_to_database_id)
    selected = [
        mention for mention in test
        if str(mention.get("gold_author_id") or "") in known_ids
    ][:args.limit]
    if len(selected) < args.limit:
        raise ValueError(
            f"requested {args.limit} known mentions, only {len(selected)} are available"
        )

    selected_by_article: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    for mention in selected:
        selected_by_article[int(mention["article_index"])].append(mention)

    audit_events: List[Mapping[str, Any]] = []
    breaker = CircuitBreaker(CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=30.0,
    ))
    runtime = IstinaProductionRuntime(
        pipeline,
        mode=RuntimeMode.SHADOW,
        circuit_breaker=breaker,
        audit_salt="istina-live-shadow",
        audit_sink=audit_events.append,
    )
    paper_latencies = []
    records = []
    authorized_commands = 0
    service_errors = 0
    for request_index, (article_index, paper_mentions) in enumerate(
        sorted(selected_by_article.items()),
        start=1,
    ):
        article = articles[article_index - 1]
        started = time.perf_counter()
        result = runtime.decide_paper(
            article,
            man_id=args.man_id,
            article_index=article_index,
            query_service=True,
            capture_legacy_shadow=True,
        )
        paper_latencies.append((time.perf_counter() - started) * 1000.0)
        authorized_commands += sum(command.authorized for command in result.commands)
        decisions_by_position = {
            str(runtime_mention.get("position") or ""): decision
            for runtime_mention, decision in zip(
                article_mentions(article, article_index=article_index),
                result.decisions,
            )
        }
        for mention in paper_mentions:
            position = str(mention.get("position") or "")
            decision = decisions_by_position.get(position)
            if decision is None:
                records.append({
                    "article_id_hash": hash_identifier(
                        mention.get("article_id"), "istina-live-shadow"
                    ),
                    "position": position,
                    "error": "selected position missing from runtime result",
                })
                service_errors += 1
                continue
            gold = str(mention.get("gold_author_id") or "")
            if decision.service_error:
                service_errors += 1
            records.append({
                "article_id_hash": hash_identifier(
                    mention.get("article_id"), "istina-live-shadow"
                ),
                "position": position,
                "gold_author_id_hash": hash_identifier(gold, "istina-live-shadow"),
                "runtime_correct": bool(
                    decision.decision == Decision.MERGE
                    and decision.author_id == gold
                ),
                "legacy_correct": decision.legacy_result_id == gold,
                "decision": decision.decision.value,
                "stage": decision.stage,
                "legacy_result_present": decision.legacy_result_id not in {
                    None, "0", "", "None"
                },
                "legacy_candidate_count": decision.legacy_candidate_count,
                "service_error": decision.service_error,
                "deterministic_hash": decision.deterministic_hash,
            })
        if request_index < len(selected_by_article) and args.sleep:
            time.sleep(args.sleep)

    raw_names = [
        str(runtime_mention.get("name") or "").strip()
        for article_index in selected_by_article
        for runtime_mention in article_mentions(
            articles[article_index - 1],
            article_index=article_index,
        )
    ]
    serialized_audit = json.dumps(audit_events, ensure_ascii=False)
    audit_redacted = all(
        not name or name not in serialized_audit
        for name in raw_names
    )
    successful = [record for record in records if not record.get("error")]
    circuit_snapshot = breaker.snapshot()
    smoke_verified = bool(
        len(successful) == args.limit
        and service_errors == 0
        and authorized_commands == 0
        and audit_redacted
        and circuit_snapshot["state"] == "closed"
    )
    minimum_release_shadow_mentions = 500
    release_shadow_verified = release_shadow_is_verified(
        smoke_verified,
        args.limit,
        minimum_release_shadow_mentions,
    )
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "dataset_name": args.dataset.name,
            "dataset_sha256": sha256_file(args.dataset),
            "mode": RuntimeMode.SHADOW.value,
            "split_strategy": args.split_strategy,
            "train_through_year": args.train_through_year,
            "service_url": args.service_url,
            "man_id": args.man_id,
            "selected_known_mentions": args.limit,
            "paper_requests": len(selected_by_article),
            "write_calls": 0,
            "raw_mentions": raw_mentions,
            "effective_mentions": len(mentions),
            "exact_duplicate_author_rows_removed": exact_duplicates_removed,
            "exact_duplicate_cleaning_applied": True,
        },
        "stats": {
            "attempted_mentions": args.limit,
            "runtime_decisions": len(successful),
            "service_successful_mentions": max(0, len(successful) - service_errors),
            "service_errors": service_errors,
            "runtime_correct": sum(record.get("runtime_correct", False) for record in successful),
            "legacy_correct": sum(record.get("legacy_correct", False) for record in successful),
            "legacy_result_present": sum(
                record.get("legacy_result_present", False) for record in successful
            ),
            "authorized_commands": authorized_commands,
        },
        "metrics": {
            "service_error_rate": service_errors / args.limit,
            "paper_round_trip_latency_ms_p50": percentile(paper_latencies, 0.50),
            "paper_round_trip_latency_ms_p95": percentile(paper_latencies, 0.95),
            "paper_round_trip_latency_ms_max": max(paper_latencies) if paper_latencies else None,
        },
        "safety": {
            "online_shadow_smoke_verified": smoke_verified,
            "audit_redacted": audit_redacted,
            "no_write_authorized": authorized_commands == 0,
            "circuit_breaker": circuit_snapshot,
        },
        "operational_evidence": {
            "online_shadow_verified": {
                "verified": release_shadow_verified,
                "smoke_verified": smoke_verified,
                "scope": "bounded live no-write shadow",
                "mentions": args.limit,
                "paper_requests": len(selected_by_article),
                "minimum_release_shadow_mentions": minimum_release_shadow_mentions,
                "sufficient_release_volume": (
                    args.limit >= minimum_release_shadow_mentions
                ),
            }
        },
        "records": records,
        "release_constraints": {
            "write_enabled_replacement_authorized": False,
            "reason": "live connectivity is verified but release sample thresholds remain unmet",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "online_shadow_smoke_verified": smoke_verified,
        "mentions": args.limit,
        "paper_requests": len(selected_by_article),
        "service_errors": service_errors,
        "authorized_commands": authorized_commands,
        "paper_latency_p95_ms": result["metrics"]["paper_round_trip_latency_ms_p95"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
