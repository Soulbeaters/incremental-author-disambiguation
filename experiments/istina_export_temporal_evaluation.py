#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproducible evaluation on an ISTINA publication export.

The benchmark simulates an import scenario:

1. Temporal mode uses publications up to ``--train-through-year`` as history.
2. Per-author holdout mode keeps each repeated author's first mention as history.
3. Remaining publications are processed as incoming mentions.
4. Mentions whose ISTINA ``author_id`` exists in history should be MERGE.
5. Mentions whose ``author_id`` is absent from history should be NEW.

The script can also query the existing ISTINA disambiguation service for a
limited subset. Service calls are intentionally optional because the remote
service is slow and sometimes times out.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.author_merger import AuthorMerger  # noqa: E402
from disambiguation_engine.decision_types import Decision  # noqa: E402
from disambiguation_engine.structured_name_repair import (  # noqa: E402
    build_repair_profiles,
    decide_structured_repair,
)
from integrations.istina_disambiguation_client import (  # noqa: E402
    DEFAULT_ISTINA_DISAMBIGUATION_URL,
    IstinaDisambiguationClient,
)
from models.author import Author  # noqa: E402
from models.database import AuthorDatabase  # noqa: E402


DEFAULT_DATASET = Path("istina test") / "chinese_articles_with_authors.json"
DEFAULT_OUTPUT = Path("results") / "istina_export_temporal_evaluation.json"


def load_articles(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of articles in {path}")
    return data


def exported_author_name(author: Dict[str, Any]) -> str:
    original = (author.get("original_name") or author.get("name") or "").strip()
    if original:
        return original
    parts = [
        (author.get("lastname") or author.get("last_name") or "").strip(),
        (author.get("firstname") or author.get("first_name") or "").strip(),
        (author.get("middlename") or author.get("middle_name") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def gold_author_id(author: Dict[str, Any]) -> Optional[str]:
    value = author.get("author_id")
    if value is None:
        value = author.get("id")
    if value is None or value == "":
        return None
    return str(value)


def article_id(article: Dict[str, Any], fallback_index: int) -> str:
    return str(article.get("id") or article.get("article_id") or article.get("doi") or fallback_index)


def iter_mentions(articles: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for article_index, article in enumerate(articles, start=1):
        authors = article.get("authors") or []
        for position, author in enumerate(authors, start=1):
            name = exported_author_name(author)
            coauthors = [
                exported_author_name(other)
                for other_pos, other in enumerate(authors, start=1)
                if other_pos != position and exported_author_name(other)
            ]
            yield {
                "article": article,
                "author": author,
                "article_index": article_index,
                "article_id": article_id(article, article_index),
                "position": author.get("position") or position,
                "year": article.get("year"),
                "doi": article.get("doi"),
                "title": article.get("title"),
                "gold_author_id": gold_author_id(author),
                "name": name,
                "lastname": (author.get("lastname") or author.get("last_name") or "").strip(),
                "firstname": (author.get("firstname") or author.get("first_name") or "").strip(),
                "middlename": (author.get("middlename") or author.get("middle_name") or "").strip(),
                "coauthors": [coauthor for coauthor in coauthors if coauthor and coauthor != name],
                "journal": article.get("journal") or article.get("venue") or "",
                "affiliation": author.get("affiliation") or "",
            }


def add_alias_blocking_keys(database: AuthorDatabase, author: Author, alias: str) -> None:
    """Index a known historical alias without creating a duplicate author."""

    alias = (alias or "").strip()
    if not alias:
        return
    surname = database._extract_surname(alias)  # private helper, used only by this experiment
    if surname:
        database.blocking_key_index[f"surname:{surname.lower()}"].append(author)
    surname_initial = database._extract_surname_initial(alias)
    if surname_initial:
        database.blocking_key_index[f"surname_init:{surname_initial}"].append(author)


def add_structured_lastname_key(database: AuthorDatabase, author: Author, lastname: str, firstname: str = "") -> None:
    lastname = (lastname or "").strip()
    if not lastname:
        return
    database.blocking_key_index[f"surname:{lastname.lower()}"].append(author)
    if firstname:
        database.blocking_key_index[f"surname_init:{lastname.lower()}_{firstname[0].lower()}"].append(author)


def build_history_database(
    history_mentions: List[Dict[str, Any]],
    index_aliases: bool = True,
) -> Tuple[AuthorDatabase, Dict[str, str]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for mention in history_mentions:
        gold = mention.get("gold_author_id")
        if gold and mention.get("name"):
            grouped[gold].append(mention)

    database = AuthorDatabase()
    gold_to_db_author_id: Dict[str, str] = {}

    for gold, mentions in sorted(grouped.items()):
        names = [mention["name"] for mention in mentions if mention.get("name")]
        canonical_name = Counter(names).most_common(1)[0][0]
        coauthors = sorted({coauthor for mention in mentions for coauthor in mention.get("coauthors", [])})
        journals = sorted({mention.get("journal") for mention in mentions if mention.get("journal")})
        affiliations = sorted({mention.get("affiliation") for mention in mentions if mention.get("affiliation")})

        author = database.add_author({
            "name": canonical_name,
            "coauthors": coauthors,
            "journals": journals,
            "affiliation": affiliations,
        })
        gold_to_db_author_id[gold] = author.author_id

        if index_aliases:
            for mention in mentions:
                author.add_alternate_name(mention["name"])
                add_alias_blocking_keys(database, author, mention["name"])
                add_structured_lastname_key(
                    database,
                    author,
                    mention.get("lastname", ""),
                    mention.get("firstname", ""),
                )

    return database, gold_to_db_author_id


def mention_payload(mention: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": mention.get("name", ""),
        "surname": mention.get("lastname", ""),
        "firstname": mention.get("firstname", ""),
        "orcid": "",
        "coauthors": mention.get("coauthors", []),
        "journals": [mention["journal"]] if mention.get("journal") else [],
        "affiliation": [mention["affiliation"]] if mention.get("affiliation") else [],
    }
    return payload


def empty_stats() -> Dict[str, int]:
    return {
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


def finalize_metrics(stats: Dict[str, int], elapsed_seconds: float) -> Dict[str, float]:
    precision = stats["correct_merge"] / stats["merge"] if stats["merge"] else 0.0
    existing_recall = (
        stats["correct_merge"] / stats["existing_gold"] if stats["existing_gold"] else 0.0
    )
    auto_accuracy = (
        (stats["correct_merge"] + stats["correct_new"]) / stats["total"]
        if stats["total"]
        else 0.0
    )
    unknown_rate = stats["unknown"] / stats["total"] if stats["total"] else 0.0
    wrong_merge_rate = stats["wrong_merge"] / stats["total"] if stats["total"] else 0.0
    f1_existing = (
        2 * precision * existing_recall / (precision + existing_recall)
        if precision + existing_recall
        else 0.0
    )
    return {
        "precision": precision,
        "existing_recall": existing_recall,
        "f1_existing": f1_existing,
        "auto_accuracy": auto_accuracy,
        "unknown_rate": unknown_rate,
        "wrong_merge_rate": wrong_merge_rate,
        "mentions_per_second": stats["total"] / elapsed_seconds if elapsed_seconds > 0 else 0.0,
    }


def evaluate_local_framework(
    database: AuthorDatabase,
    gold_to_db_author_id: Dict[str, str],
    test_mentions: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    merger = AuthorMerger(
        database=database,
        mode=args.mode,
        accept_threshold=args.accept_threshold,
        reject_threshold=args.reject_threshold,
        min_accept_margin=args.min_accept_margin,
        require_context_for_low_name_accept=args.require_context_for_low_name_accept,
        topk=args.topk,
    )

    stats = empty_stats()
    errors: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    db_to_gold_author_id = {
        db_author_id: gold for gold, db_author_id in gold_to_db_author_id.items()
    }
    start = time.perf_counter()

    for mention in test_mentions:
        gold = mention.get("gold_author_id")
        if not gold:
            continue

        gold_db_id = gold_to_db_author_id.get(gold)
        stats["total"] += 1
        if gold_db_id:
            stats["existing_gold"] += 1
        else:
            stats["new_gold"] += 1

        result = merger.make_decision(mention_payload(mention), metadata={
            "article_id": mention.get("article_id"),
            "position": mention.get("position"),
            "year": mention.get("year"),
        })
        records.append({
            "article_index": mention.get("article_index"),
            "article_id": mention.get("article_id"),
            "year": mention.get("year"),
            "position": mention.get("position"),
            "name": mention.get("name"),
            "gold_author_id": gold,
            "gold_seen_in_history": bool(gold_db_id),
            "decision": result.decision.value,
            "predicted_db_author_id": result.best_author_id,
            "predicted_gold_author_id": db_to_gold_author_id.get(result.best_author_id),
            "score": result.score_total,
            "candidate_count": result.candidate_count,
            "comparisons": result.comparisons,
            "topk": result.topk,
        })

        if result.decision == Decision.MERGE:
            stats["merge"] += 1
            if gold_db_id and result.best_author_id == gold_db_id:
                stats["correct_merge"] += 1
            else:
                stats["wrong_merge"] += 1
                if not gold_db_id:
                    stats["merge_for_new_gold"] += 1
                if len(errors) < args.error_sample_limit:
                    errors.append({
                        "type": "wrong_merge",
                        "article_id": mention.get("article_id"),
                        "year": mention.get("year"),
                        "position": mention.get("position"),
                        "name": mention.get("name"),
                        "gold_author_id": gold,
                        "gold_seen_in_history": bool(gold_db_id),
                        "predicted_db_author_id": result.best_author_id,
                        "score": result.score_total,
                        "comparisons": result.comparisons,
                        "topk": result.topk,
                    })
        elif result.decision == Decision.NEW:
            stats["new"] += 1
            if gold_db_id:
                stats["false_new_for_existing"] += 1
                if len(errors) < args.error_sample_limit:
                    errors.append({
                        "type": "false_new_for_existing",
                        "article_id": mention.get("article_id"),
                        "year": mention.get("year"),
                        "position": mention.get("position"),
                        "name": mention.get("name"),
                        "gold_author_id": gold,
                        "score": result.score_total,
                        "comparisons": result.comparisons,
                    })
            else:
                stats["correct_new"] += 1
        else:
            stats["unknown"] += 1

    elapsed = time.perf_counter() - start
    return {
        "stats": stats,
        "metrics": finalize_metrics(stats, elapsed),
        "elapsed_seconds": elapsed,
        "error_samples": errors,
        "records": records,
    }


def evaluate_service(
    service_mentions: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    client = IstinaDisambiguationClient(args.service_url, timeout=args.service_timeout)
    stats = {
        "attempted": 0,
        "ok": 0,
        "errors": 0,
        "nonzero_result": 0,
        "result_matches_gold": 0,
        "gold_in_candidates": 0,
    }
    records: List[Dict[str, Any]] = []

    for mention in service_mentions:
        query = client.from_exported_author(mention["author"], repair_short_family=True)
        stats["attempted"] += 1
        try:
            response = client.request_candidates([query], man_id=args.man_id)
        except Exception as exc:  # service diagnostic: preserve exact failure
            stats["errors"] += 1
            records.append({
                "article_id": mention.get("article_id"),
                "name": mention.get("name"),
                "gold_author_id": mention.get("gold_author_id"),
                "query": query.as_payload(),
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        candidates = (response.get("authors") or [[]])[0]
        candidate_ids = [str(candidate.get("id")) for candidate in candidates]
        result_id = str((response.get("result_id") or ["0"])[0])
        gold = mention.get("gold_author_id")
        stats["ok"] += 1
        stats["nonzero_result"] += int(result_id not in ("0", "", "None"))
        stats["result_matches_gold"] += int(result_id == gold)
        stats["gold_in_candidates"] += int(gold in candidate_ids)
        records.append({
            "article_id": mention.get("article_id"),
            "year": mention.get("year"),
            "position": mention.get("position"),
            "name": mention.get("name"),
            "gold_author_id": gold,
            "query": query.as_payload(),
            "parsed": response.get("authors_names"),
            "result_id": result_id,
            "result_matches_gold": result_id == gold,
            "gold_in_candidates": gold in candidate_ids,
            "candidate_count": len(candidates),
            "top_candidate": candidates[0] if candidates else None,
            "candidates": candidates,
        })
        if args.service_sleep:
            time.sleep(args.service_sleep)

    precision = stats["result_matches_gold"] / stats["ok"] if stats["ok"] else 0.0
    return {
        "stats": stats,
        "metrics": {
            "result_match_rate": precision,
            "gold_candidate_recall": stats["gold_in_candidates"] / stats["ok"] if stats["ok"] else 0.0,
        },
        "records": records,
    }


def evaluate_service_papers(
    service_mentions: List[Dict[str, Any]],
    all_mentions: List[Dict[str, Any]],
    args: argparse.Namespace,
    client: Optional[IstinaDisambiguationClient] = None,
) -> Dict[str, Any]:
    """Query the legacy service with complete paper author lists.

    The legacy hypergraph model selects an author combination for a paper, so
    this is the fair comparison mode.  Metrics are still counted only for the
    selected target mentions.
    """

    client = client or IstinaDisambiguationClient(
        args.service_url,
        timeout=args.service_timeout,
    )
    context_by_article: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    targets_by_article: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for mention in all_mentions:
        context_by_article[int(mention["article_index"])].append(mention)
    for mention in service_mentions:
        targets_by_article[int(mention["article_index"])].append(mention)

    stats = {
        "attempted": 0,
        "ok": 0,
        "errors": 0,
        "requests": 0,
        "nonzero_result": 0,
        "result_matches_gold": 0,
        "gold_in_candidates": 0,
    }
    records: List[Dict[str, Any]] = []

    for article_index, targets in sorted(targets_by_article.items()):
        context = context_by_article[article_index]
        context_index = {
            mention_identity(mention): index for index, mention in enumerate(context)
        }
        queries = [
            client.from_exported_author(mention["author"], repair_short_family=True)
            for mention in context
        ]
        stats["attempted"] += len(targets)
        stats["requests"] += 1
        try:
            response = client.request_candidates(queries, man_id=args.man_id)
        except Exception as exc:
            stats["errors"] += len(targets)
            for target in targets:
                target_index = context_index[mention_identity(target)]
                records.append({
                    "article_index": article_index,
                    "article_id": target.get("article_id"),
                    "year": target.get("year"),
                    "position": target.get("position"),
                    "name": target.get("name"),
                    "gold_author_id": target.get("gold_author_id"),
                    "query": queries[target_index].as_payload(),
                    "error": f"{type(exc).__name__}: {exc}",
                })
            continue

        candidate_groups = response.get("authors") or []
        parsed_names = response.get("authors_names") or []
        result_ids = response.get("result_id") or []
        for target in targets:
            target_index = context_index[mention_identity(target)]
            if target_index >= len(result_ids):
                stats["errors"] += 1
                records.append({
                    "article_index": article_index,
                    "article_id": target.get("article_id"),
                    "year": target.get("year"),
                    "position": target.get("position"),
                    "name": target.get("name"),
                    "gold_author_id": target.get("gold_author_id"),
                    "query": queries[target_index].as_payload(),
                    "error": "service_response_missing_result_position",
                })
                continue

            candidates = candidate_groups[target_index] if target_index < len(candidate_groups) else []
            candidate_ids = [str(candidate.get("id")) for candidate in candidates]
            result_id = str(result_ids[target_index])
            gold = target.get("gold_author_id")
            stats["ok"] += 1
            stats["nonzero_result"] += int(result_id not in ("0", "", "None"))
            stats["result_matches_gold"] += int(result_id == gold)
            stats["gold_in_candidates"] += int(gold in candidate_ids)
            records.append({
                "article_index": article_index,
                "article_id": target.get("article_id"),
                "year": target.get("year"),
                "position": target.get("position"),
                "name": target.get("name"),
                "gold_author_id": gold,
                "query": queries[target_index].as_payload(),
                "parsed": parsed_names[target_index] if target_index < len(parsed_names) else None,
                "result_id": result_id,
                "result_matches_gold": result_id == gold,
                "gold_in_candidates": gold in candidate_ids,
                "candidate_count": len(candidates),
                "top_candidate": candidates[0] if candidates else None,
                "candidates": candidates,
            })
        if args.service_sleep:
            time.sleep(args.service_sleep)

    return {
        "stats": stats,
        "metrics": {
            "result_match_rate": (
                stats["result_matches_gold"] / stats["ok"] if stats["ok"] else 0.0
            ),
            "gold_candidate_recall": (
                stats["gold_in_candidates"] / stats["ok"] if stats["ok"] else 0.0
            ),
        },
        "records": records,
    }


def evaluate_known_author_unknown_fallback(
    service_result: Dict[str, Any],
    known_author_ids: Iterable[str],
    min_name_similarity: float,
    local_candidate_ids: Optional[Mapping[Tuple[str, str, str, str, str], Iterable[str]]] = None,
) -> Dict[str, Any]:
    stats = {
        "attempted": 0,
        "accepted": 0,
        "correct": 0,
        "wrong": 0,
        "rejected": 0,
        "service_errors": 0,
    }
    records: List[Dict[str, Any]] = []
    known_ids = {str(author_id) for author_id in known_author_ids}
    for record in service_result.get("records") or []:
        stats["attempted"] += 1
        if record.get("error"):
            stats["service_errors"] += 1
            records.append({
                "article_id": record.get("article_id"),
                "article_index": record.get("article_index"),
                "position": record.get("position"),
                "name": record.get("name"),
                "accepted": False,
                "reason": "service_error",
            })
            continue

        eligible_ids = known_ids
        if local_candidate_ids is not None:
            eligible_ids = {
                str(author_id)
                for author_id in local_candidate_ids.get(mention_identity(record), ())
            }
            raw_result_id = record.get("result_id")
            if isinstance(raw_result_id, (list, tuple)):
                service_result_id = str(raw_result_id[0]) if raw_result_id else "0"
            else:
                service_result_id = str(raw_result_id or "0")
            if service_result_id in known_ids and service_result_id not in eligible_ids:
                stats["rejected"] += 1
                records.append({
                    "article_id": record.get("article_id"),
                    "article_index": record.get("article_index"),
                    "position": record.get("position"),
                    "name": record.get("name"),
                    "gold_author_id": record.get("gold_author_id"),
                    "accepted": False,
                    "correct": False,
                    "reason": "service_result_not_local_candidate",
                    "candidate_id": None,
                })
                continue

        response = {
            "authors": [record.get("candidates") or []],
            "result_id": [record.get("result_id")],
        }
        decision = IstinaDisambiguationClient.known_author_unknown_fallback(
            response,
            known_author_ids=eligible_ids,
            min_name_similarity=min_name_similarity,
        )
        correct = bool(
            decision.accepted
            and decision.candidate
            and decision.candidate.id == str(record.get("gold_author_id"))
        )
        stats["accepted"] += int(decision.accepted)
        stats["correct"] += int(correct)
        stats["wrong"] += int(decision.accepted and not correct)
        stats["rejected"] += int(not decision.accepted)
        records.append({
            "article_id": record.get("article_id"),
            "article_index": record.get("article_index"),
            "position": record.get("position"),
            "name": record.get("name"),
            "gold_author_id": record.get("gold_author_id"),
            "accepted": decision.accepted,
            "correct": correct,
            "reason": decision.reason,
            "candidate_id": decision.candidate.id if decision.candidate else None,
        })

    return {
        "stats": stats,
        "metrics": {
            "precision": stats["correct"] / stats["accepted"] if stats["accepted"] else 0.0,
            "coverage": stats["accepted"] / stats["attempted"] if stats["attempted"] else 0.0,
        },
        "records": records,
    }


def combine_local_with_unknown_fallback(
    local_result: Dict[str, Any],
    fallback_result: Dict[str, Any],
) -> Dict[str, Any]:
    stats = dict(local_result["stats"])
    fallback_stats = fallback_result["stats"]
    accepted = fallback_stats["accepted"]
    if accepted > stats["unknown"]:
        raise ValueError("Fallback accepted more mentions than the local UNKNOWN pool")

    stats["unknown"] -= accepted
    stats["merge"] += accepted
    stats["correct_merge"] += fallback_stats["correct"]
    stats["wrong_merge"] += fallback_stats["wrong"]
    metrics = finalize_metrics(stats, elapsed_seconds=0.0)
    metrics.pop("mentions_per_second")
    return {"stats": stats, "metrics": metrics}


def evaluate_structured_name_repair(
    history_mentions: List[Dict[str, Any]],
    test_mentions: List[Dict[str, Any]],
    local_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluate the conservative second pass on local NEW/UNKNOWN records."""

    profiles = build_repair_profiles(history_mentions)
    local_by_identity = {
        mention_identity(record): record for record in local_records
    }
    stats = {
        "attempted": 0,
        "accepted": 0,
        "correct": 0,
        "wrong": 0,
        "accepted_from_new": 0,
        "accepted_from_unknown": 0,
    }
    records: List[Dict[str, Any]] = []
    for mention in test_mentions:
        local_record = local_by_identity[mention_identity(mention)]
        base_decision = local_record.get("decision")
        if base_decision not in {Decision.NEW.value, Decision.UNKNOWN.value}:
            continue

        stats["attempted"] += 1
        decision = decide_structured_repair(mention, profiles)
        correct = bool(
            decision.accepted
            and decision.author_id == str(mention.get("gold_author_id"))
        )
        stats["accepted"] += int(decision.accepted)
        stats["correct"] += int(correct)
        stats["wrong"] += int(decision.accepted and not correct)
        if decision.accepted:
            stats[f"accepted_from_{base_decision}"] += 1
        records.append({
            "article_index": mention.get("article_index"),
            "article_id": mention.get("article_id"),
            "year": mention.get("year"),
            "position": mention.get("position"),
            "name": mention.get("name"),
            "gold_author_id": mention.get("gold_author_id"),
            "gold_seen_in_history": local_record.get("gold_seen_in_history"),
            "base_decision": base_decision,
            "accepted": decision.accepted,
            "correct": correct,
            "reason": decision.reason,
            "candidate_id": decision.author_id,
            "relation": decision.relation,
            "coauthor_jaccard": decision.coauthor_jaccard,
            "history_name": decision.history_name,
        })

    return {
        "stats": stats,
        "metrics": {
            "precision": stats["correct"] / stats["accepted"] if stats["accepted"] else 0.0,
            "coverage": stats["accepted"] / stats["attempted"] if stats["attempted"] else 0.0,
        },
        "quarantined_history_author_ids": list(profiles.quarantined_author_ids),
        "records": records,
    }


def combine_local_with_structured_repair(
    local_result: Dict[str, Any],
    repair_result: Dict[str, Any],
) -> Dict[str, Any]:
    stats = dict(local_result["stats"])
    for record in repair_result.get("records") or []:
        if not record.get("accepted"):
            continue
        base_decision = record.get("base_decision")
        if base_decision == Decision.NEW.value:
            stats["new"] -= 1
            if record.get("gold_seen_in_history"):
                stats["false_new_for_existing"] -= 1
            else:
                stats["correct_new"] -= 1
        elif base_decision == Decision.UNKNOWN.value:
            stats["unknown"] -= 1
        else:
            raise ValueError(f"Unexpected structured-repair base decision: {base_decision}")

        stats["merge"] += 1
        if record.get("correct"):
            stats["correct_merge"] += 1
        else:
            stats["wrong_merge"] += 1
            if not record.get("gold_seen_in_history"):
                stats["merge_for_new_gold"] += 1

    metrics = finalize_metrics(stats, elapsed_seconds=0.0)
    metrics.pop("mentions_per_second")
    return {"stats": stats, "metrics": metrics}


def select_service_mentions(
    test_mentions: List[Dict[str, Any]],
    history_gold_ids: Iterable[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """Select the shared existing-author task for a fair service comparison.

    The local framework can correctly classify an unseen author as NEW, while
    the production ISTINA service searches the full database and is expected to
    return that author's global ID.  Such cases have incompatible targets, so
    the head-to-head subset contains only gold authors represented in the local
    history database.
    """

    seen = set(history_gold_ids)
    eligible = [
        mention
        for mention in test_mentions
        if mention.get("gold_author_id") in seen
    ]
    if limit:
        return eligible[:limit]
    return eligible


def mention_identity(mention: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        str(mention.get("article_index")),
        str(mention.get("article_id")),
        str(mention.get("position")),
        str(mention.get("gold_author_id")),
        str(mention.get("name")),
    )


def select_local_decision_mentions(
    test_mentions: List[Dict[str, Any]],
    local_records: List[Dict[str, Any]],
    decision: str,
    limit: int,
) -> List[Dict[str, Any]]:
    selected_keys = {
        mention_identity(record)
        for record in local_records
        if record.get("decision") == decision
    }
    eligible = [
        mention
        for mention in test_mentions
        if mention_identity(mention) in selected_keys
    ]
    return eligible[:limit] if limit else eligible


def dataset_summary(mentions: List[Dict[str, Any]], train_through_year: int) -> Dict[str, Any]:
    years: Dict[str, int] = defaultdict(int)
    gold_counter: Counter[str] = Counter()
    for mention in mentions:
        years[str(mention.get("year"))] += 1
        if mention.get("gold_author_id"):
            gold_counter[mention["gold_author_id"]] += 1
    return {
        "mentions": len(mentions),
        "mentions_with_gold": sum(1 for mention in mentions if mention.get("gold_author_id")),
        "unique_gold_author_ids": len(gold_counter),
        "multi_mention_gold_author_ids": sum(1 for count in gold_counter.values() if count > 1),
        "years": dict(sorted(years.items())),
        "train_through_year": train_through_year,
    }


def split_mentions(
    mentions: List[Dict[str, Any]],
    strategy: str,
    train_through_year: int,
    include_singleton_new_gold: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if strategy == "temporal":
        history_mentions = [
            mention for mention in mentions if mention.get("year") and mention["year"] <= train_through_year
        ]
        test_mentions = [
            mention for mention in mentions if mention.get("year") and mention["year"] > train_through_year
        ]
        return history_mentions, test_mentions

    if strategy != "per-author-holdout":
        raise ValueError(f"Unsupported split strategy: {strategy}")

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    missing_gold: List[Dict[str, Any]] = []
    for mention in mentions:
        gold = mention.get("gold_author_id")
        if gold:
            grouped[gold].append(mention)
        else:
            missing_gold.append(mention)

    history_mentions: List[Dict[str, Any]] = []
    test_mentions: List[Dict[str, Any]] = []
    for _gold, group in sorted(grouped.items()):
        ordered = sorted(
            group,
            key=lambda item: (
                item.get("year") or 0,
                item.get("article_index") or 0,
                item.get("position") or 0,
            ),
        )
        if len(ordered) >= 2:
            history_mentions.append(ordered[0])
            test_mentions.extend(ordered[1:])
        elif include_singleton_new_gold:
            test_mentions.append(ordered[0])

    return history_mentions, test_mentions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--split-strategy",
        choices=["temporal", "per-author-holdout"],
        default="temporal",
    )
    parser.add_argument("--train-through-year", type=int, default=2023)
    parser.add_argument("--mode", choices=["baseline", "fs"], default="fs")
    parser.add_argument("--accept-threshold", type=float, default=-2.0)
    parser.add_argument("--reject-threshold", type=float, default=-4.0)
    parser.add_argument("--min-accept-margin", type=float, default=1e-9)
    parser.add_argument("--require-context-for-low-name-accept", action="store_true")
    parser.add_argument("--enable-structured-repair", action="store_true")
    parser.add_argument("--disable-alias-index", action="store_true")
    parser.add_argument("--exclude-singleton-new-gold", action="store_true")
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--error-sample-limit", type=int, default=25)
    parser.add_argument("--compare-service", action="store_true")
    parser.add_argument(
        "--service-subset",
        choices=["shared-existing", "local-unknown"],
        default="shared-existing",
    )
    parser.add_argument(
        "--service-request-mode",
        choices=["paper", "mention"],
        default="paper",
    )
    parser.add_argument("--service-url", default=DEFAULT_ISTINA_DISAMBIGUATION_URL)
    parser.add_argument("--man-id", type=int, default=4705445)
    parser.add_argument("--service-limit", type=int, default=20)
    parser.add_argument("--service-timeout", type=float, default=20.0)
    parser.add_argument("--service-sleep", type=float, default=0.05)
    parser.add_argument("--service-fallback-min-name-similarity", type=float, default=0.85)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    articles = load_articles(args.dataset)
    mentions = list(iter_mentions(articles))
    history_mentions, test_mentions = split_mentions(
        mentions,
        strategy=args.split_strategy,
        train_through_year=args.train_through_year,
        include_singleton_new_gold=not args.exclude_singleton_new_gold,
    )

    database, gold_to_db_author_id = build_history_database(
        history_mentions,
        index_aliases=not args.disable_alias_index,
    )
    db_author_to_gold = {
        db_author_id: gold_author_id
        for gold_author_id, db_author_id in gold_to_db_author_id.items()
    }
    local_result = evaluate_local_framework(database, gold_to_db_author_id, test_mentions, args)
    structured_repair_result = (
        evaluate_structured_name_repair(
            history_mentions,
            test_mentions,
            local_result["records"],
        )
        if args.enable_structured_repair
        else None
    )
    local_after_structured_repair = (
        combine_local_with_structured_repair(local_result, structured_repair_result)
        if structured_repair_result
        else local_result
    )
    service_mentions: List[Dict[str, Any]] = []
    if args.compare_service:
        if args.service_subset == "shared-existing":
            service_mentions = select_service_mentions(
                test_mentions,
                gold_to_db_author_id,
                args.service_limit,
            )
        else:
            service_mentions = select_local_decision_mentions(
                test_mentions,
                local_result["records"],
                Decision.UNKNOWN.value,
                0,
            )
            if structured_repair_result:
                repaired_unknown = {
                    mention_identity(record)
                    for record in structured_repair_result["records"]
                    if record.get("accepted")
                    and record.get("base_decision") == Decision.UNKNOWN.value
                }
                service_mentions = [
                    mention for mention in service_mentions
                    if mention_identity(mention) not in repaired_unknown
                ]
            if args.service_limit:
                service_mentions = service_mentions[:args.service_limit]
    local_service_subset_result = (
        evaluate_local_framework(database, gold_to_db_author_id, service_mentions, args)
        if args.compare_service
        else None
    )
    service_result = None
    if args.compare_service:
        service_result = (
            evaluate_service_papers(service_mentions, mentions, args)
            if args.service_request_mode == "paper"
            else evaluate_service(service_mentions, args)
        )
    service_fallback_result = (
        evaluate_known_author_unknown_fallback(
            service_result,
            known_author_ids=gold_to_db_author_id,
            min_name_similarity=args.service_fallback_min_name_similarity,
            local_candidate_ids={
                mention_identity(record): {
                    db_author_to_gold[item["author_id"]]
                    for item in record.get("topk") or []
                    if item.get("author_id") in db_author_to_gold
                }
                for record in (local_service_subset_result or {}).get("records", [])
            },
        )
        if service_result and args.service_subset == "local-unknown"
        else None
    )
    combined_result = (
        combine_local_with_unknown_fallback(
            local_after_structured_repair,
            service_fallback_result,
        )
        if service_fallback_result
        else local_after_structured_repair if structured_repair_result else None
    )

    result = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "dataset": str(args.dataset),
            "split_strategy": args.split_strategy,
            "train_through_year": args.train_through_year,
            "mode": args.mode,
            "accept_threshold": args.accept_threshold,
            "reject_threshold": args.reject_threshold,
            "min_accept_margin": args.min_accept_margin,
            "require_context_for_low_name_accept": args.require_context_for_low_name_accept,
            "enable_structured_repair": args.enable_structured_repair,
            "alias_index": not args.disable_alias_index,
            "include_singleton_new_gold": not args.exclude_singleton_new_gold,
            "compare_service": args.compare_service,
            "service_limit": args.service_limit if args.compare_service else 0,
            "service_subset": args.service_subset,
            "service_request_mode": args.service_request_mode,
            "service_fallback_min_name_similarity": args.service_fallback_min_name_similarity,
        },
        "dataset_summary": dataset_summary(mentions, args.train_through_year),
        "split": {
            "history_mentions": len(history_mentions),
            "test_mentions": len(test_mentions),
            "history_authors_with_gold": len(gold_to_db_author_id),
            "database_authors": database.get_author_count(),
        },
        "local_framework": local_result,
        "structured_name_repair": structured_repair_result,
        "local_after_structured_repair": (
            local_after_structured_repair if structured_repair_result else None
        ),
        "local_framework_service_subset": local_service_subset_result,
        "istina_service": service_result,
        "known_author_unknown_fallback": service_fallback_result,
        "combined_local_and_unknown_fallback": combined_result,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(json.dumps({
        "dataset_summary": result["dataset_summary"],
        "split": result["split"],
        "local_framework": {
            "stats": local_result["stats"],
            "metrics": local_result["metrics"],
        },
        "structured_name_repair": {
            "stats": structured_repair_result["stats"],
            "metrics": structured_repair_result["metrics"],
        } if structured_repair_result else None,
        "local_after_structured_repair": (
            local_after_structured_repair if structured_repair_result else None
        ),
        "local_framework_service_subset": {
            "stats": local_service_subset_result["stats"],
            "metrics": local_service_subset_result["metrics"],
        } if local_service_subset_result else None,
        "istina_service": {
            "stats": service_result["stats"],
            "metrics": service_result["metrics"],
        } if service_result else None,
        "known_author_unknown_fallback": {
            "stats": service_fallback_result["stats"],
            "metrics": service_fallback_result["metrics"],
        } if service_fallback_result else None,
        "combined_local_and_unknown_fallback": combined_result,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
