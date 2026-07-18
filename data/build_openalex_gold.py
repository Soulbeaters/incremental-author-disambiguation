"""Build a reproducible cross-domain author gold set from the OpenAlex API.

OpenAlex author IDs are labels only. They are not emitted as model features.
The output keeps raw author-name variants, coauthors, venue, institution, year,
field, and domain so the runtime pipeline can be evaluated without ORCID.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

import requests


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SELECT_FIELDS = ",".join([
    "id",
    "doi",
    "title",
    "publication_year",
    "authorships",
    "primary_location",
    "primary_topic",
])


def short_openalex_id(value: str) -> str:
    return str(value or "").rstrip("/").rsplit("/", 1)[-1]


def split_display_name(value: str) -> Tuple[str, str, str]:
    """Conservative OpenAlex display-name split with an auditable source."""

    value = " ".join(str(value or "").strip().split())
    if not value:
        return "", "", "missing"
    if "," in value:
        family, given = (part.strip() for part in value.split(",", 1))
        return family, given, "comma_family_first"
    parts = value.split()
    if len(parts) == 1:
        return parts[0], "", "single_token"
    return parts[-1], " ".join(parts[:-1]), "openalex_display_given_first"


def author_name(authorship: Mapping[str, Any]) -> str:
    return str(
        authorship.get("raw_author_name")
        or (authorship.get("author") or {}).get("display_name")
        or ""
    ).strip()


def first_affiliation(authorship: Mapping[str, Any]) -> str:
    raw = list(authorship.get("raw_affiliation_strings") or [])
    if raw:
        return str(raw[0])
    institutions = list(authorship.get("institutions") or [])
    if institutions:
        return str(institutions[0].get("display_name") or "")
    return ""


def source_name(work: Mapping[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return str(source.get("display_name") or location.get("raw_source_name") or "")


def work_mentions(work: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    authorships = [
        authorship for authorship in work.get("authorships") or []
        if (authorship.get("author") or {}).get("id") and author_name(authorship)
    ]
    names = [author_name(authorship) for authorship in authorships]
    topic = work.get("primary_topic") or {}
    field = topic.get("field") or {}
    domain = topic.get("domain") or {}
    work_id = short_openalex_id(work.get("id"))
    for position, (authorship, name) in enumerate(zip(authorships, names), start=1):
        family, given, split_source = split_display_name(name)
        author = authorship.get("author") or {}
        yield {
            "mention_id": f"{work_id}:{position}",
            "article_id": work_id,
            "doi": str(work.get("doi") or "").removeprefix("https://doi.org/"),
            "title": str(work.get("title") or ""),
            "year": work.get("publication_year"),
            "position": position,
            "author_id": short_openalex_id(author.get("id")),
            "name": name,
            "lastname": family,
            "firstname": given,
            "name_split_source": split_source,
            "coauthors": [
                other for other_index, other in enumerate(names)
                if other_index != position - 1 and other and other != name
            ],
            "journal": source_name(work),
            "affiliation": first_affiliation(authorship),
            "field": str(field.get("display_name") or ""),
            "domain": str(domain.get("display_name") or ""),
            "source": "openalex_api",
        }


def request_page(
    session: requests.Session,
    params: Mapping[str, Any],
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = session.get(OPENALEX_WORKS_URL, params=params, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"OpenAlex returned HTTP {response.status_code}",
                    response=response,
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
    raise RuntimeError(f"OpenAlex request failed: {last_error}")


def build_dataset(args: argparse.Namespace) -> Dict[str, Any]:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pages = math.ceil(args.sample_works / args.per_page)
    filters = (
        f"from_publication_date:{args.from_year}-01-01,"
        f"to_publication_date:{args.to_year}-12-31"
    )
    session = requests.Session()
    if args.email:
        session.headers.update({"User-Agent": f"istina-author-research mailto:{args.email}"})

    mention_count = 0
    work_count = 0
    works_with_mentions = 0
    seen_work_ids: set[str] = set()
    duplicate_work_ids = 0
    author_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    split_source_counts: Counter[str] = Counter()
    started = time.perf_counter()
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for page in range(1, pages + 1):
            remaining = args.sample_works - work_count
            if remaining <= 0:
                break
            data = request_page(
                session,
                {
                    "filter": filters,
                    "sample": args.sample_works,
                    "seed": args.seed,
                    "per-page": min(args.per_page, remaining),
                    "page": page,
                    "select": SELECT_FIELDS,
                },
                timeout=args.timeout,
                retries=args.retries,
            )
            works = list(data.get("results") or [])
            if not works:
                break
            for work in works:
                work_count += 1
                work_id = short_openalex_id(work.get("id"))
                if work_id in seen_work_ids:
                    duplicate_work_ids += 1
                    continue
                seen_work_ids.add(work_id)
                mentions = list(work_mentions(work))
                if mentions:
                    works_with_mentions += 1
                for mention in mentions:
                    handle.write(json.dumps(mention, ensure_ascii=False) + "\n")
                    mention_count += 1
                    author_counts[mention["author_id"]] += 1
                    field_counts[mention["field"] or "Unknown"] += 1
                    domain_counts[mention["domain"] or "Unknown"] += 1
                    split_source_counts[mention["name_split_source"]] += 1
            if args.sleep:
                time.sleep(args.sleep)

    elapsed = time.perf_counter() - started
    repeated_authors = {author_id: count for author_id, count in author_counts.items() if count >= 2}
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": "OpenAlex API",
            "url": OPENALEX_WORKS_URL,
            "documentation": "https://docs.openalex.org/",
            "openalex_paper_doi": "10.1038/s41597-022-01371-4",
        },
        "request": {
            "sample_works": args.sample_works,
            "seed": args.seed,
            "from_year": args.from_year,
            "to_year": args.to_year,
            "select": SELECT_FIELDS,
        },
        "counts": {
            "works": work_count,
            "unique_works": len(seen_work_ids),
            "duplicate_work_ids_skipped": duplicate_work_ids,
            "works_with_mentions": works_with_mentions,
            "works_without_mentions": len(seen_work_ids) - works_with_mentions,
            "mentions": mention_count,
            "unique_authors": len(author_counts),
            "repeated_authors": len(repeated_authors),
            "mentions_from_repeated_authors": sum(repeated_authors.values()),
        },
        "field_counts": dict(field_counts.most_common()),
        "domain_counts": dict(domain_counts.most_common()),
        "name_split_source_counts": dict(split_source_counts.most_common()),
        "elapsed_seconds": elapsed,
        "output": str(args.output),
        "gold_policy": "OpenAlex author ID used only for split and evaluation",
    }
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-works", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--from-year", type=int, default=2010)
    parser.add_argument("--to-year", type=int, default=2025)
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--email")
    parser.add_argument("--output", type=Path, default=Path("data/openalex_gold_mentions.jsonl"))
    parser.add_argument("--metadata", type=Path, default=Path("data/openalex_gold_metadata.json"))
    args = parser.parse_args()
    if not 1 <= args.sample_works <= 10_000:
        parser.error("sample-works must be within OpenAlex's deterministic sample limit [1, 10000]")
    if not 1 <= args.per_page <= 200:
        parser.error("per-page must be within [1, 200]")
    if args.from_year > args.to_year:
        parser.error("from-year must not exceed to-year")

    print(json.dumps(build_dataset(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
