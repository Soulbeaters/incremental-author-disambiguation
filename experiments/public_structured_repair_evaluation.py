"""Author-disjoint safety evaluation for structured name repair.

ORCID labels are used only to create the split and score decisions. They are
never passed to the repair model. Entire held-out authors exercise the critical
failure mode: linking a genuinely new author to a known profile merely because
their names are equal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.structured_name_repair import (  # noqa: E402
    build_repair_profiles,
    decide_structured_repair,
)


def load_mentions(path: Path) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            records[str(record["mention_id"])] = record
    return records


def load_clusters(path: Path) -> Mapping[str, List[str]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["clusters"]


def adapt_mention(record: Mapping[str, Any], author_id: str) -> Dict[str, Any]:
    adapted = dict(record)
    adapted["gold_author_id"] = author_id
    adapted["name"] = str(record.get("raw_name") or "")
    adapted["article_id"] = str(record.get("doi") or "")
    return adapted


def split_author_disjoint(
    mentions: Mapping[str, Dict[str, Any]],
    clusters: Mapping[str, List[str]],
    holdout_modulus: int,
    holdout_bucket: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], frozenset[str]]:
    history: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    unseen_author_ids = set()
    for author_id in sorted(clusters):
        rows = [adapt_mention(mentions[mention_id], author_id) for mention_id in clusters[author_id]]
        bucket = int(hashlib.sha256(author_id.encode("utf-8")).hexdigest(), 16) % holdout_modulus
        if bucket == holdout_bucket:
            unseen_author_ids.add(author_id)
            test.extend(rows)
            continue
        cut = len(rows) // 2
        history.extend(rows[:cut])
        test.extend(rows[cut:])
    return history, test, frozenset(unseen_author_ids)


def evaluate(
    history: Iterable[Mapping[str, Any]],
    test: Iterable[Mapping[str, Any]],
    unseen_author_ids: frozenset[str],
) -> Dict[str, Any]:
    history_rows = list(history)
    test_rows = list(test)
    profiles = build_repair_profiles(history_rows)
    stats = {
        "history_mentions": len(history_rows),
        "test_mentions": len(test_rows),
        "existing_test_mentions": 0,
        "unseen_test_mentions": 0,
        "unseen_test_authors": len(unseen_author_ids),
        "history_mentions_with_coauthors": sum(bool(row.get("coauthors")) for row in history_rows),
        "test_mentions_with_coauthors": sum(bool(row.get("coauthors")) for row in test_rows),
        "accepted": 0,
        "correct": 0,
        "wrong": 0,
        "accepted_existing": 0,
        "correct_existing": 0,
        "accepted_unseen": 0,
        "wrong_unseen": 0,
    }
    error_samples = []
    for row in test_rows:
        unseen = str(row["gold_author_id"]) in unseen_author_ids
        stats["unseen_test_mentions" if unseen else "existing_test_mentions"] += 1
        decision = decide_structured_repair(row, profiles)
        if not decision.accepted:
            continue
        correct = decision.author_id == str(row["gold_author_id"])
        stats["accepted"] += 1
        stats["correct"] += int(correct)
        stats["wrong"] += int(not correct)
        stats["accepted_unseen" if unseen else "accepted_existing"] += 1
        if unseen:
            stats["wrong_unseen"] += int(not correct)
        else:
            stats["correct_existing"] += int(correct)
        if not correct and len(error_samples) < 50:
            error_samples.append({
                "mention_id": row.get("mention_id"),
                "name": row.get("raw_name"),
                "gold_author_id": row.get("gold_author_id"),
                "candidate_id": decision.author_id,
                "unseen_author": unseen,
                "relation": decision.relation,
                "coauthor_jaccard": decision.coauthor_jaccard,
            })

    return {
        "stats": stats,
        "metrics": {
            "accepted_precision": stats["correct"] / stats["accepted"] if stats["accepted"] else None,
            "existing_recall": (
                stats["correct_existing"] / stats["existing_test_mentions"]
                if stats["existing_test_mentions"] else None
            ),
            "unseen_false_link_rate": (
                stats["wrong_unseen"] / stats["unseen_test_mentions"]
                if stats["unseen_test_mentions"] else None
            ),
        },
        "quarantined_history_author_ids": list(profiles.quarantined_author_ids),
        "error_samples": error_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mentions", type=Path, default=PROJECT_ROOT / "data" / "mentions.jsonl")
    parser.add_argument("--clusters", type=Path, default=PROJECT_ROOT / "data" / "gold_clusters.json")
    parser.add_argument("--holdout-modulus", type=int, default=5)
    parser.add_argument("--holdout-bucket", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.holdout_modulus < 2 or not 0 <= args.holdout_bucket < args.holdout_modulus:
        parser.error("holdout bucket must be within a modulus of at least two")

    mentions = load_mentions(args.mentions)
    clusters = load_clusters(args.clusters)
    history, test, unseen = split_author_disjoint(
        mentions,
        clusters,
        args.holdout_modulus,
        args.holdout_bucket,
    )
    result = {
        "protocol": {
            "mentions": str(args.mentions),
            "clusters": str(args.clusters),
            "unseen_rule": f"int(sha256(orcid), 16) mod {args.holdout_modulus} == {args.holdout_bucket}",
            "known_author_split": "first floor(n/2) history, remainder test",
            "identity_used_only_for_split_and_evaluation": True,
        },
        **evaluate(history, test, unseen),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
