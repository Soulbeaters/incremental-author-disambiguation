"""Run a bounded, no-write live shadow through the production safety runtime."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.decision_types import Decision  # noqa: E402
from evaluation.istina_paired_shadow import assess_paired_shadow_plan  # noqa: E402
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
from integrations.istina_observability import (  # noqa: E402
    TamperEvidentJsonlAuditSink,
    verify_audit_chain,
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
    return hmac.new(
        salt.encode("utf-8"),
        str(value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]


def audit_stream_is_redacted(path: Path, forbidden_values: List[str]) -> bool:
    """Scan line-by-line so release-scale audit files are never loaded whole."""

    needles = [value for value in forbidden_values if value]
    with path.open("r", encoding="utf-8") as handle:
        return all(
            not any(needle in line for needle in needles)
            for line in handle
        )


def release_shadow_is_verified(
    smoke_verified: bool,
    mentions: int,
    minimum_mentions: int = 500,
    *,
    papers: int | None = None,
    minimum_papers: int = 0,
) -> bool:
    """Require both a healthy smoke and release-scale online volume."""

    papers_verified = minimum_papers <= 0 or (
        papers is not None and papers >= minimum_papers
    )
    return bool(
        smoke_verified
        and mentions >= minimum_mentions
        and papers_verified
    )


def select_known_shadow_mentions(
    mentions: List[Mapping[str, Any]],
    known_ids: set[str],
    *,
    limit: int,
    minimum_papers: int = 0,
) -> List[Mapping[str, Any]]:
    """Select a deterministic, outcome-blind sample with paper coverage."""

    eligible = [
        mention
        for mention in mentions
        if str(mention.get("gold_author_id") or "") in known_ids
    ]
    if len(eligible) < limit:
        raise ValueError(
            f"requested {limit} known mentions, only {len(eligible)} are available"
        )
    if minimum_papers <= 0:
        return eligible[:limit]

    first_from_each_paper: List[Mapping[str, Any]] = []
    covered_papers = set()
    for mention in eligible:
        paper = int(mention["article_index"])
        if paper in covered_papers:
            continue
        covered_papers.add(paper)
        first_from_each_paper.append(mention)
        if len(first_from_each_paper) == minimum_papers:
            break
    if len(first_from_each_paper) < minimum_papers:
        raise ValueError(
            f"known mentions cover {len(first_from_each_paper)} papers; "
            f"paired-shadow plan requires {minimum_papers}"
        )

    selected_keys = {
        (int(mention["article_index"]), str(mention.get("position") or ""))
        for mention in first_from_each_paper
    }
    selected = list(first_from_each_paper)
    for mention in eligible:
        key = (
            int(mention["article_index"]),
            str(mention.get("position") or ""),
        )
        if key in selected_keys:
            continue
        selected.append(mention)
        selected_keys.add(key)
        if len(selected) == limit:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--man-id", type=int, default=4705445)
    parser.add_argument("--service-url", default=DEFAULT_ISTINA_DISAMBIGUATION_URL)
    parser.add_argument("--service-timeout", type=float, default=20.0)
    parser.add_argument(
        "--code-revision",
        help=(
            "Frozen 40-hex Git revision; required for institutional deployment "
            "evidence, optional for bounded connectivity smoke runs."
        ),
    )
    parser.add_argument(
        "--paired-shadow-plan",
        type=Path,
        help=(
            "Approved preregistration plan. When supplied, the runner validates "
            "it before collection and enforces its mention and paper targets."
        ),
    )
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Retained private audit JSONL; omit only for an ephemeral smoke chain.",
    )
    parser.add_argument(
        "--audit-salt-env",
        default="ISTINA_AUDIT_SALT",
        help="Environment variable containing the private HMAC audit salt.",
    )
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
    if args.code_revision and re.fullmatch(
        r"[0-9a-fA-F]{40}", args.code_revision
    ) is None:
        raise ValueError("code-revision must be a full 40-hex Git commit")
    paired_plan_assessment = None
    paired_plan_sha256 = None
    if args.paired_shadow_plan:
        if not args.code_revision:
            raise ValueError(
                "paired-shadow-plan requires a full --code-revision"
            )
        paired_plan_document = json.loads(
            args.paired_shadow_plan.read_text(encoding="utf-8")
        )
        if not isinstance(paired_plan_document, Mapping):
            raise ValueError("paired-shadow-plan must contain a JSON object")
        paired_plan_sha256 = sha256_file(args.paired_shadow_plan)
        paired_plan_assessment = assess_paired_shadow_plan(
            paired_plan_document,
            expected_dataset_sha256=sha256_file(args.dataset),
            expected_code_revision=args.code_revision,
        )
        if not paired_plan_assessment["verified"]:
            failed = ", ".join(
                item["name"] for item in paired_plan_assessment["failures"]
            )
            raise ValueError(f"paired-shadow plan preflight failed: {failed}")
        planned_mentions = int(
            paired_plan_assessment["power_plan"][
                "effective_required_mentions"
            ]
        )
        if args.limit < planned_mentions:
            raise ValueError(
                f"limit {args.limit} is below paired-shadow target "
                f"{planned_mentions}"
            )

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
    minimum_unique_papers = int(
        paired_plan_assessment["power_plan"]["minimum_unique_papers"]
        if paired_plan_assessment is not None
        else 0
    )
    selected = select_known_shadow_mentions(
        test,
        known_ids,
        limit=args.limit,
        minimum_papers=minimum_unique_papers,
    )

    selected_by_article: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    for mention in selected:
        selected_by_article[int(mention["article_index"])].append(mention)

    configured_audit_salt = os.environ.get(args.audit_salt_env, "").strip()
    if args.audit_output and not configured_audit_salt:
        raise ValueError(
            f"retained audit output requires non-empty {args.audit_salt_env}"
        )
    audit_salt = configured_audit_salt or secrets.token_hex(32)
    temporary_audit_directory = None
    if args.audit_output:
        audit_path = args.audit_output
        audit_retained = True
    else:
        temporary_audit_directory = tempfile.TemporaryDirectory(
            prefix="istina-live-shadow-audit-"
        )
        audit_path = Path(temporary_audit_directory.name) / "audit.jsonl"
        audit_retained = False
    audit_sink = TamperEvidentJsonlAuditSink(audit_path, fsync=True)
    audit_start_records = audit_sink.snapshot()["records"]
    breaker = CircuitBreaker(CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=30.0,
    ))
    runtime = IstinaProductionRuntime(
        pipeline,
        mode=RuntimeMode.SHADOW,
        circuit_breaker=breaker,
        audit_salt=audit_salt,
        audit_sink=audit_sink,
    )
    paper_latencies = []
    records = []
    authorized_commands = 0
    service_errors = 0
    expected_audit_records = 0
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
        expected_audit_records += len(result.decisions)
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
                        mention.get("article_id"), audit_salt
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
                    mention.get("article_id"), audit_salt
                ),
                "position": position,
                "gold_author_id_hash": hash_identifier(gold, audit_salt),
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
                "service_error": bool(decision.service_error),
                "deterministic_hash": hash_identifier(
                    decision.deterministic_hash,
                    audit_salt,
                ),
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
    chain_report = verify_audit_chain(audit_path)
    audit_records_appended = chain_report["records"] - audit_start_records
    durable_audit_verified = bool(
        chain_report["verified"]
        and audit_records_appended == expected_audit_records
        and audit_sink.snapshot()["fsync"]
    )
    audit_redacted = audit_stream_is_redacted(audit_path, raw_names)
    successful = [record for record in records if not record.get("error")]
    circuit_snapshot = breaker.snapshot()
    smoke_verified = bool(
        len(successful) == args.limit
        and service_errors == 0
        and authorized_commands == 0
        and audit_redacted
        and durable_audit_verified
        and circuit_snapshot["state"] == "closed"
    )
    minimum_release_shadow_mentions = max(
        500,
        int(
            paired_plan_assessment["power_plan"][
                "effective_required_mentions"
            ]
            if paired_plan_assessment is not None
            else 0
        ),
    )
    release_shadow_verified = release_shadow_is_verified(
        smoke_verified,
        args.limit,
        minimum_release_shadow_mentions,
        papers=len(selected_by_article),
        minimum_papers=minimum_unique_papers,
    )
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "dataset_name": args.dataset.name,
            "dataset_sha256": sha256_file(args.dataset),
            "code_revision": (
                args.code_revision.lower() if args.code_revision else None
            ),
            "paired_shadow_plan_sha256": paired_plan_sha256,
            "paired_shadow_required_mentions": (
                minimum_release_shadow_mentions
                if paired_plan_assessment is not None
                else None
            ),
            "paired_shadow_minimum_unique_papers": (
                minimum_unique_papers
                if paired_plan_assessment is not None
                else None
            ),
            "mode": RuntimeMode.SHADOW.value,
            "split_strategy": args.split_strategy,
            "train_through_year": args.train_through_year,
            "service_url": args.service_url,
            "man_id_hash": hash_identifier(args.man_id, audit_salt),
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
            "durable_audit_chain": {
                "verified": durable_audit_verified,
                "records_appended": audit_records_appended,
                "chain_records_total": chain_report["records"],
                "head_hash": chain_report["head_hash"],
                "fsync": audit_sink.snapshot()["fsync"],
                "retained": audit_retained,
                "storage_scope": (
                    "operator-supplied retained private JSONL"
                    if audit_retained
                    else "ephemeral smoke validation JSONL"
                ),
            },
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
                "minimum_release_shadow_papers": minimum_unique_papers,
                "sufficient_release_papers": (
                    len(selected_by_article) >= minimum_unique_papers
                ),
            }
        },
        "records": records,
        "release_constraints": {
            "write_enabled_replacement_authorized": False,
            "reason": (
                "live shadow evidence alone never authorizes writes; the final "
                "machine release gate must pass every check"
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if temporary_audit_directory is not None:
        temporary_audit_directory.cleanup()
    print(json.dumps({
        "output": str(args.output),
        "online_shadow_smoke_verified": smoke_verified,
        "mentions": args.limit,
        "paper_requests": len(selected_by_article),
        "service_errors": service_errors,
        "authorized_commands": authorized_commands,
        "durable_audit_chain_verified": durable_audit_verified,
        "audit_retained": audit_retained,
        "paper_latency_p95_ms": result["metrics"]["paper_round_trip_latency_ms_p95"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
