"""Replay the formal ISTINA runtime pipeline on a gold publication export."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.decision_types import Decision  # noqa: E402
from experiments.istina_export_temporal_evaluation import (  # noqa: E402
    iter_mentions,
    load_articles,
    mention_identity,
    split_mentions,
)
from integrations.istina_pipeline import (  # noqa: E402
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
)
from integrations.istina_export_quality import (  # noqa: E402
    deduplicate_exact_author_rows,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Iterable[float], quantile: float) -> Optional[float]:
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def load_service_records(path: Optional[Path]) -> Dict[Tuple[str, str, str, str, str], Dict[str, Any]]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        mention_identity(record): record
        for record in (data.get("istina_service") or {}).get("records", [])
        if not record.get("error")
    }


def record_service_response(record: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not record:
        return None
    return {
        "authors": [list(record.get("candidates") or [])],
        "result_id": [record.get("result_id")],
        "authors_names": [record.get("parsed")],
    }


def exact_mcnemar_two_sided(new_only: int, old_only: int) -> float:
    discordant = new_only + old_only
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(new_only, old_only) + 1)
    ) / (2 ** discordant)
    return min(1.0, 2.0 * tail)


def evaluate(
    pipeline: IstinaDisambiguationPipeline,
    test_mentions: List[Dict[str, Any]],
    service_records: Mapping[Tuple[str, str, str, str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    known_ids = set(pipeline.history_state.external_to_database_id)
    stats = {
        "total": 0,
        "existing_gold": 0,
        "new_gold": 0,
        "merge": 0,
        "new": 0,
        "unknown": 0,
        "correct_merge": 0,
        "wrong_merge": 0,
        "correct_new": 0,
        "false_new_for_existing": 0,
        "merge_for_new_gold": 0,
    }
    stage_counts: Counter[str] = Counter()
    retrieval = {
        "truncated_mentions": 0,
        "candidate_pool_total": 0,
        "scored_candidate_total": 0,
    }
    latencies = []
    records = []
    error_samples = []
    paired = {
        "both_correct": 0,
        "runtime_only_correct": 0,
        "legacy_only_correct": 0,
        "both_incorrect": 0,
    }
    started = time.perf_counter()

    for mention in test_mentions:
        gold = str(mention.get("gold_author_id") or "")
        if not gold:
            continue
        service_record = service_records.get(mention_identity(mention))
        result = pipeline.decide_mention(
            mention,
            service_response=record_service_response(service_record),
        )
        seen = gold in known_ids
        correct_merge = result.decision == Decision.MERGE and result.author_id == gold
        stats["total"] += 1
        stats["existing_gold" if seen else "new_gold"] += 1
        stats[result.decision.value] += 1
        stage_counts[result.stage] += 1
        retrieval["candidate_pool_total"] += result.candidate_count
        retrieval["scored_candidate_total"] += result.scored_candidate_count
        if result.candidate_pool_truncated:
            retrieval["truncated_mentions"] += 1
        latencies.append(result.latency_ms)

        if result.decision == Decision.MERGE:
            stats["correct_merge" if correct_merge else "wrong_merge"] += 1
            if not seen:
                stats["merge_for_new_gold"] += 1
        elif result.decision == Decision.NEW:
            if seen:
                stats["false_new_for_existing"] += 1
            else:
                stats["correct_new"] += 1

        # A fair incumbent comparison is defined only for gold identities that
        # are present in the frozen history.  After export de-duplication, some
        # records from an older sample are correctly reclassified as new.
        if service_record and seen:
            legacy_correct = str(service_record.get("result_id")) == gold
            cell = (
                "both_correct" if correct_merge and legacy_correct else
                "runtime_only_correct" if correct_merge else
                "legacy_only_correct" if legacy_correct else
                "both_incorrect"
            )
            paired[cell] += 1

        record = {
            "article_index": mention.get("article_index"),
            "article_id": mention.get("article_id"),
            "position": mention.get("position"),
            "name": mention.get("name"),
            "gold_author_id": gold,
            "gold_seen_in_history": seen,
            "correct": bool(correct_merge or (result.decision == Decision.NEW and not seen)),
            **result.to_dict(),
        }
        records.append(record)
        if (
            (result.decision == Decision.MERGE and not correct_merge)
            or (seen and result.decision != Decision.MERGE)
        ) and len(error_samples) < 50:
            error_samples.append(record)

    elapsed = time.perf_counter() - started
    precision = stats["correct_merge"] / stats["merge"] if stats["merge"] else 0.0
    recall = stats["correct_merge"] / stats["existing_gold"] if stats["existing_gold"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    discordant_new = paired["runtime_only_correct"]
    discordant_old = paired["legacy_only_correct"]
    shadow_total = sum(paired.values())
    return {
        "stats": stats,
        "metrics": {
            "precision": precision,
            "existing_recall": recall,
            "f1_existing": f1,
            "auto_accuracy": (
                (stats["correct_merge"] + stats["correct_new"]) / stats["total"]
                if stats["total"] else 0.0
            ),
            "unknown_rate": stats["unknown"] / stats["total"] if stats["total"] else 0.0,
            "wrong_merge_rate": stats["wrong_merge"] / stats["total"] if stats["total"] else 0.0,
            "throughput_mentions_per_second": stats["total"] / elapsed if elapsed else None,
            "latency_ms_p50": percentile(latencies, 0.50),
            "latency_ms_p95": percentile(latencies, 0.95),
            "latency_ms_p99": percentile(latencies, 0.99),
            "latency_ms_max": max(latencies) if latencies else None,
        },
        "stage_counts": dict(sorted(stage_counts.items())),
        "candidate_retrieval": {
            **retrieval,
            "average_candidate_pool_size": (
                retrieval["candidate_pool_total"] / stats["total"]
                if stats["total"] else 0.0
            ),
            "average_scored_candidate_count": (
                retrieval["scored_candidate_total"] / stats["total"]
                if stats["total"] else 0.0
            ),
        },
        "legacy_shadow": {
            "n": shadow_total,
            "paired_table": paired,
            "runtime_correct": paired["both_correct"] + paired["runtime_only_correct"],
            "legacy_correct": paired["both_correct"] + paired["legacy_only_correct"],
            "mcnemar_exact_two_sided_p": (
                exact_mcnemar_two_sided(discordant_new, discordant_old)
                if shadow_total else None
            ),
        },
        "elapsed_seconds": elapsed,
        "error_samples": error_samples,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split-strategy", choices=["temporal", "per-author-holdout"], default="per-author-holdout")
    parser.add_argument("--train-through-year", type=int, default=2023)
    parser.add_argument("--service-result", type=Path)
    parser.add_argument(
        "--keep-exact-duplicate-author-rows",
        action="store_true",
        help="diagnostic only: bypass safe exact-row de-duplication",
    )
    parser.add_argument(
        "--compact-output",
        action="store_true",
        help="omit mention-level records and error samples from the output file",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    raw_articles = load_articles(args.dataset)
    raw_mentions = sum(len(article.get("authors") or []) for article in raw_articles)
    if args.keep_exact_duplicate_author_rows:
        articles = raw_articles
        exact_duplicates_removed = 0
    else:
        articles, exact_duplicates_removed = deduplicate_exact_author_rows(
            raw_articles
        )
    mentions = list(iter_mentions(articles))
    history, test = split_mentions(
        mentions,
        args.split_strategy,
        args.train_through_year,
    )
    config = IstinaPipelineConfig(
        mode="fs",
        accept_threshold=-0.5,
        reject_threshold=-4.0,
        min_accept_margin=1e-9,
        require_context_for_low_name_accept=True,
    )
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(history, config=config)
    result = {
        "protocol": {
            "dataset": str(args.dataset),
            "dataset_sha256": sha256_file(args.dataset),
            "split_strategy": args.split_strategy,
            "train_through_year": args.train_through_year,
            "history_mentions": len(history),
            "test_mentions": len(test),
            "raw_mentions": raw_mentions,
            "effective_mentions": len(mentions),
            "exact_duplicate_author_rows_removed": exact_duplicates_removed,
            "exact_duplicate_cleaning_applied": (
                not args.keep_exact_duplicate_author_rows
            ),
            "service_result": str(args.service_result) if args.service_result else None,
            "service_result_sha256": (
                sha256_file(args.service_result) if args.service_result else None
            ),
            "runtime_class": "integrations.istina_pipeline.IstinaDisambiguationPipeline",
        },
        **evaluate(pipeline, test, load_service_records(args.service_result)),
    }
    summary = {
        key: value
        for key, value in result.items()
        if key not in {"records", "error_samples"}
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output_document = summary if args.compact_output else result
        args.output.write_text(
            json.dumps(output_document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
