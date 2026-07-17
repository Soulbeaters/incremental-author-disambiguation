#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose ISTINA disambiguation service behavior on short family names.

The current ISTINA service may parse a short family name without patronymic
as initials. Example: Ma Jiaxin can become M.A. Jiaxin. This script compares:

1. baseline request as exported;
2. query-only repaired request with a dummy middle name for short surnames.

It does not modify source data and does not trust the service result blindly.
The optional local accept rule is intentionally conservative and exists only
for diagnosis.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


DEFAULT_SERVICE_URL = "http://93.180.23.185:9091/"
DEFAULT_DATASET = Path("istina test") / "chinese_articles_with_authors.json"


def _clean(value: str) -> str:
    value = (value or "").lower().strip()
    return "".join(ch for ch in value if ch.isalnum())


def load_articles(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected list of articles in {path}")
    return data


def iter_author_mentions(articles: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for article in articles:
        for author in article.get("authors", []) or []:
            row = dict(author)
            row["article_id"] = article.get("id")
            row["year"] = article.get("year")
            row["doi"] = article.get("doi")
            yield row


def has_short_family_without_middle(author: Dict[str, Any]) -> bool:
    last_name = (author.get("lastname") or "").strip()
    first_name = (author.get("firstname") or "").strip()
    middle_name = (author.get("middlename") or "").strip()
    compact_last_name = "".join(ch for ch in last_name if ch.isalpha())
    return bool(last_name and first_name and not middle_name and len(compact_last_name) <= 2)


def build_service_author(author: Dict[str, Any], repair: bool) -> Dict[str, str]:
    last_name = (author.get("lastname") or "").strip()
    first_name = (author.get("firstname") or "").strip()
    middle_name = (author.get("middlename") or "").strip()

    # Some exported Chinese names can be stored as "Li Hui" in lastname.
    # Split only for query construction, never mutate the input dataset.
    if repair and not first_name and not middle_name and " " in last_name:
        parts = [part for part in last_name.split() if part]
        if len(parts) == 2:
            last_name, first_name = parts

    if repair and last_name and first_name and not middle_name:
        compact_last_name = "".join(ch for ch in last_name if ch.isalpha())
        if len(compact_last_name) <= 2:
            has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in last_name + first_name)
            middle_name = "ч" if has_cyrillic else "x"

    return {
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": middle_name,
    }


def call_service(
    service_url: str,
    service_author: Dict[str, str],
    man_id: int,
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    payload = {"authors": [service_author], "man_id": man_id}
    last_error: Optional[str] = None
    for _attempt in range(retries + 1):
        try:
            response = requests.post(
                service_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=timeout,
            )
            response.raise_for_status()
            return json.loads(response.content.decode("utf-8", errors="replace"))
        except Exception as exc:  # diagnostic script: preserve exact service failure
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
    return {"_error": last_error}


def choose_conservative_candidate(
    query: Dict[str, str],
    service_response: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Accept only one unambiguous exact candidate and service agreement."""

    query_last = _clean(query["last_name"])
    query_first = _clean(query["first_name"])

    if len(query_first) <= 1:
        return None, "ambiguous_initial_firstname"

    service_result_id = str((service_response.get("result_id") or ["0"])[0])
    groups = service_response.get("authors") or [[]]
    candidates = groups[0] if groups else []

    exact_candidates: List[Dict[str, Any]] = []
    for candidate in candidates:
        candidate_last = _clean(candidate.get("last_name") or "")
        candidate_first = _clean(candidate.get("first_name") or "")
        similarity = float(candidate.get("name_similarity") or 0.0)
        if (
            candidate_last == query_last
            and candidate_first == query_first
            and similarity >= 0.84
        ):
            exact_candidates.append(candidate)

    if len(exact_candidates) == 1 and str(exact_candidates[0].get("id")) == service_result_id:
        return exact_candidates[0], "service_agrees_with_unique_exact_candidate"

    return None, "not_unique_exact_or_service_disagrees"


def summarize_dataset(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    mentions = list(iter_author_mentions(articles))
    years: Dict[str, int] = {}
    for article in articles:
        year = str(article.get("year"))
        years[year] = years.get(year, 0) + 1

    return {
        "articles": len(articles),
        "years": dict(sorted(years.items())),
        "author_mentions": len(mentions),
        "unique_nonempty_author_ids": len(
            {author.get("author_id") for author in mentions if author.get("author_id") is not None}
        ),
        "missing_author_id": sum(1 for author in mentions if author.get("author_id") is None),
        "missing_lastname": sum(1 for author in mentions if not (author.get("lastname") or "").strip()),
        "missing_firstname": sum(1 for author in mentions if not (author.get("firstname") or "").strip()),
        "missing_middlename": sum(1 for author in mentions if not (author.get("middlename") or "").strip()),
        "short_family_without_middle": sum(has_short_family_without_middle(author) for author in mentions),
    }


def run_diagnostic(args: argparse.Namespace) -> Dict[str, Any]:
    articles = load_articles(args.dataset)
    mentions = list(iter_author_mentions(articles))
    target_mentions = [author for author in mentions if has_short_family_without_middle(author)]

    records: List[Dict[str, Any]] = []
    aggregate = {
        "baseline": {
            "ok": 0,
            "errors": 0,
            "nonzero_result": 0,
            "result_matches_author_id": 0,
            "gold_in_candidates": 0,
        },
        "repaired": {
            "ok": 0,
            "errors": 0,
            "nonzero_result": 0,
            "result_matches_author_id": 0,
            "gold_in_candidates": 0,
        },
        "conservative_local_rule": {
            "gold_present": 0,
            "gold_missing": 0,
            "accepted_gold_present": 0,
            "accepted_gold_correct": 0,
            "accepted_gold_wrong": 0,
            "accepted_gold_missing": 0,
            "unknown": 0,
        },
    }

    for index, mention in enumerate(target_mentions, start=1):
        gold = str(mention.get("author_id")) if mention.get("author_id") is not None else None
        row = {
            "index": index,
            "article_id": mention.get("article_id"),
            "year": mention.get("year"),
            "doi": mention.get("doi"),
            "original_name": mention.get("original_name"),
            "lastname": mention.get("lastname"),
            "firstname": mention.get("firstname"),
            "middlename": mention.get("middlename"),
            "author_id": gold,
        }
        service_responses: Dict[str, Dict[str, Any]] = {}

        for mode, repair in (("baseline", False), ("repaired", True)):
            query = build_service_author(mention, repair=repair)
            response = call_service(args.service_url, query, args.man_id, args.timeout, args.retries)
            service_responses[mode] = response
            if args.sleep:
                time.sleep(args.sleep)

            if "_error" in response:
                aggregate[mode]["errors"] += 1
                row[mode] = {"ok": False, "query": query, "error": response["_error"]}
                continue

            candidates = (response.get("authors") or [[]])[0]
            candidate_ids = [str(candidate.get("id")) for candidate in candidates]
            result_id = str((response.get("result_id") or ["0"])[0])
            aggregate[mode]["ok"] += 1
            aggregate[mode]["nonzero_result"] += int(result_id not in ("0", "", "None"))
            aggregate[mode]["result_matches_author_id"] += int(bool(gold and result_id == gold))
            aggregate[mode]["gold_in_candidates"] += int(bool(gold and gold in candidate_ids))
            row[mode] = {
                "ok": True,
                "query": query,
                "parsed": response.get("authors_names"),
                "result_id": result_id,
                "candidate_count": len(candidates),
                "result_matches_author_id": bool(gold and result_id == gold),
                "gold_in_candidates": bool(gold and gold in candidate_ids),
                "gold_rank": candidate_ids.index(gold) + 1 if gold and gold in candidate_ids else None,
                "top_candidate": candidates[0] if candidates else None,
            }

        repaired = row.get("repaired") or {}
        if gold:
            aggregate["conservative_local_rule"]["gold_present"] += 1
        else:
            aggregate["conservative_local_rule"]["gold_missing"] += 1

        if repaired.get("ok"):
            chosen, reason = choose_conservative_candidate(
                repaired["query"],
                service_responses.get("repaired") or {},
            )
            row["local_conservative"] = {
                "chosen": chosen,
                "reason": reason,
                "matches_author_id": bool(chosen and gold and str(chosen.get("id")) == gold),
            }
            if chosen:
                if gold:
                    aggregate["conservative_local_rule"]["accepted_gold_present"] += 1
                    if str(chosen.get("id")) == gold:
                        aggregate["conservative_local_rule"]["accepted_gold_correct"] += 1
                    else:
                        aggregate["conservative_local_rule"]["accepted_gold_wrong"] += 1
                else:
                    aggregate["conservative_local_rule"]["accepted_gold_missing"] += 1
            else:
                aggregate["conservative_local_rule"]["unknown"] += 1
        else:
            aggregate["conservative_local_rule"]["unknown"] += 1

        records.append(row)
        if args.limit and index >= args.limit:
            break

    return {
        "service_url": args.service_url,
        "dataset": str(args.dataset),
        "dataset_summary": summarize_dataset(articles),
        "target_mentions": len(target_mentions if not args.limit else target_mentions[: args.limit]),
        "aggregate": aggregate,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--service-url", default=DEFAULT_SERVICE_URL)
    parser.add_argument("--man-id", type=int, default=4705445)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("results") / "istina_service_short_name_diagnostic.json")
    args = parser.parse_args()

    result = run_diagnostic(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(json.dumps({
        "dataset_summary": result["dataset_summary"],
        "target_mentions": result["target_mentions"],
        "aggregate": result["aggregate"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
