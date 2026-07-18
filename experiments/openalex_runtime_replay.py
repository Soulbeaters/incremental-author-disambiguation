"""Replay the formal ISTINA runtime on a public OpenAlex authorship gold set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.istina_export_temporal_evaluation import split_mentions  # noqa: E402
from experiments.istina_runtime_replay import evaluate  # noqa: E402
from integrations.istina_pipeline import (  # noqa: E402
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
)


def load_mentions(path: Path) -> List[Dict[str, Any]]:
    mentions = []
    with path.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            mention = json.loads(line)
            author_id = str(
                mention.get("gold_author_id")
                or mention.get("author_id")
                or ""
            )
            if not author_id or not mention.get("name"):
                continue
            mention["gold_author_id"] = author_id
            mention["article_index"] = row_index
            mentions.append(mention)
    return mentions


def split_orcid_author_holdout(
    mentions: List[Dict[str, Any]],
    known_author_fraction: float = 2.0 / 3.0,
    history_papers_per_known_author: int = 1,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Create known and unseen authors without splitting any publication."""

    if not 0.0 < known_author_fraction < 1.0:
        raise ValueError("known_author_fraction must be within (0, 1)")
    if history_papers_per_known_author < 1:
        raise ValueError("history_papers_per_known_author must be positive")
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for mention in mentions:
        grouped[str(mention["gold_author_id"])].append(mention)
    history_article_ids = set()
    threshold = int(known_author_fraction * 10_000)
    for author_id, group in sorted(grouped.items()):
        bucket = int(hashlib.sha256(author_id.encode("utf-8")).hexdigest()[:8], 16) % 10_000
        if bucket >= threshold:
            continue
        ordered = sorted(
            group,
            key=lambda item: (
                item.get("year") or 0,
                item.get("article_id") or "",
                item.get("position") or 0,
            ),
        )
        selected = []
        selected_ids = set()
        for mention in ordered:
            article_id = str(mention["article_id"])
            if article_id in selected_ids:
                continue
            selected.append(article_id)
            selected_ids.add(article_id)
            if len(selected) >= history_papers_per_known_author:
                break
        history_article_ids.update(selected)
    history = [
        mention for mention in mentions
        if str(mention.get("article_id")) in history_article_ids
    ]
    test = [
        mention for mention in mentions
        if str(mention.get("article_id")) not in history_article_ids
    ]
    return history, test


def split_article_holdout(
    mentions: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep complete papers on one side while exposing repeated identities.

    The first chronological paper of every repeated OpenAlex author is added
    to history. All authorships from that paper stay in history, preventing
    coauthor/journal/affiliation leakage from one paper into both partitions.
    """

    author_counts = Counter(str(mention["gold_author_id"]) for mention in mentions)
    repeated = {author_id for author_id, count in author_counts.items() if count >= 2}
    first_by_author: Dict[str, Dict[str, Any]] = {}
    for mention in sorted(
        mentions,
        key=lambda item: (
            item.get("year") or 0,
            item.get("article_id") or "",
            item.get("position") or 0,
        ),
    ):
        author_id = str(mention["gold_author_id"])
        if author_id in repeated and author_id not in first_by_author:
            first_by_author[author_id] = mention
    history_article_ids = {
        str(mention["article_id"]) for mention in first_by_author.values()
    }
    history = [
        mention for mention in mentions
        if str(mention.get("article_id")) in history_article_ids
    ]
    test = [
        mention for mention in mentions
        if str(mention.get("article_id")) not in history_article_ids
    ]
    return history, test


def _empty_slice() -> Dict[str, int]:
    return {
        "total": 0,
        "existing_gold": 0,
        "new_gold": 0,
        "correct": 0,
        "merge": 0,
        "wrong_merge": 0,
        "unknown": 0,
        "false_new_for_existing": 0,
    }


def _finalize_slice(stats: Mapping[str, int]) -> Dict[str, Any]:
    total = stats["total"]
    merge = stats["merge"]
    existing = stats["existing_gold"]
    correct_merge = merge - stats["wrong_merge"]
    return {
        **stats,
        "accuracy": stats["correct"] / total if total else None,
        "merge_precision": correct_merge / merge if merge else None,
        "existing_recall": (
            correct_merge / existing if existing else None
        ),
        "unknown_rate": stats["unknown"] / total if total else None,
        "wrong_merge_rate": stats["wrong_merge"] / total if total else None,
    }


def slice_metrics(
    test_mentions: Iterable[Mapping[str, Any]],
    records: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    dimensions = ("domain", "field", "name_split_source")
    grouped: Dict[str, Dict[str, Dict[str, int]]] = {
        dimension: defaultdict(_empty_slice) for dimension in dimensions
    }
    for mention, record in zip(test_mentions, records):
        for dimension in dimensions:
            key = str(mention.get(dimension) or "Unknown")
            stats = grouped[dimension][key]
            stats["total"] += 1
            seen = bool(record.get("gold_seen_in_history"))
            stats["existing_gold" if seen else "new_gold"] += 1
            stats["correct"] += int(bool(record.get("correct")))
            decision = str(record.get("decision") or "")
            stats["merge"] += int(decision == "merge")
            stats["wrong_merge"] += int(
                decision == "merge"
                and str(record.get("author_id") or "")
                != str(record.get("gold_author_id") or "")
            )
            stats["unknown"] += int(decision == "unknown")
            stats["false_new_for_existing"] += int(seen and decision == "new")
    return {
        dimension: {
            key: _finalize_slice(values)
            for key, values in sorted(groups.items())
        }
        for dimension, groups in grouped.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/openalex_gold_mentions.jsonl"),
    )
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--split-strategy",
        choices=[
            "article-holdout",
            "orcid-author-holdout",
            "temporal",
            "per-author-holdout",
        ],
        default="article-holdout",
    )
    parser.add_argument("--train-through-year", type=int, default=2020)
    parser.add_argument("--known-author-fraction", type=float, default=2.0 / 3.0)
    parser.add_argument("--history-papers-per-known-author", type=int, default=1)
    parser.add_argument("--accept-threshold", type=float, default=-0.5)
    parser.add_argument("--reject-threshold", type=float, default=-4.0)
    parser.add_argument("--min-accept-margin", type=float, default=1e-9)
    args = parser.parse_args()

    mentions = load_mentions(args.dataset)
    if args.split_strategy == "article-holdout":
        history, test = split_article_holdout(mentions)
        split_description = (
            "complete first chronological paper for each repeated author in history; "
            "all remaining complete papers in test"
        )
    elif args.split_strategy == "orcid-author-holdout":
        history, test = split_orcid_author_holdout(
            mentions,
            known_author_fraction=args.known_author_fraction,
            history_papers_per_known_author=args.history_papers_per_known_author,
        )
        split_description = (
            "deterministic author-disjoint known/unseen assignment; first complete "
            f"{args.history_papers_per_known_author} paper(s) of each known anchor "
            "in history; no publication overlap"
        )
    else:
        history, test = split_mentions(
            mentions,
            args.split_strategy,
            train_through_year=args.train_through_year,
            include_singleton_new_gold=True,
        )
        split_description = args.split_strategy
    config = IstinaPipelineConfig(
        mode="fs",
        accept_threshold=args.accept_threshold,
        reject_threshold=args.reject_threshold,
        min_accept_margin=args.min_accept_margin,
        require_context_for_low_name_accept=True,
        use_remote_fallback=False,
    )
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(history, config=config)
    evaluation = evaluate(pipeline, test, service_records={})
    metadata = (
        json.loads(args.metadata.read_text(encoding="utf-8"))
        if args.metadata else None
    )
    gold_label = (
        "ORCID identity (evaluation only; hidden from runtime)"
        if metadata and str(metadata.get("gold_policy") or "").startswith("ORCID")
        else "OpenAlex author ID (evaluation only)"
    )
    result = {
        "protocol": {
            "dataset": str(args.dataset),
            "source": "OpenAlex API",
            "gold_label": gold_label,
            "split_strategy": split_description,
            "train_through_year": (
                args.train_through_year if args.split_strategy == "temporal" else None
            ),
            "known_author_fraction": (
                args.known_author_fraction
                if args.split_strategy == "orcid-author-holdout" else None
            ),
            "history_papers_per_known_author": (
                args.history_papers_per_known_author
                if args.split_strategy == "orcid-author-holdout" else None
            ),
            "article_overlap": len(
                {str(row.get("article_id")) for row in history}
                & {str(row.get("article_id")) for row in test}
            ),
            "history_mentions": len(history),
            "test_mentions": len(test),
            "runtime_class": "integrations.istina_pipeline.IstinaDisambiguationPipeline",
            "metadata": metadata,
        },
        **evaluation,
    }
    result["slices"] = slice_metrics(test, result["records"])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    summary = {
        key: value
        for key, value in result.items()
        if key not in {"records", "error_samples", "slices"}
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
