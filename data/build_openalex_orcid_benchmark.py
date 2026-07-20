"""Build a reproducible ORCID-labelled, ORCID-blind OpenAlex benchmark."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data.build_openalex_gold import (
    SELECT_FIELDS,
    author_name,
    first_affiliation,
    short_openalex_id,
    source_name,
    split_display_name,
)


AUTHORS_URL = "https://api.openalex.org/authors"
WORKS_URL = "https://api.openalex.org/works"
AUTHOR_SELECT = "id,display_name,orcid,works_count"


def normalized_orcid(value: Any) -> str:
    return str(value or "").strip().rstrip("/").rsplit("/", 1)[-1].upper()


def request_json(
    session: requests.Session,
    url: str,
    params: Mapping[str, Any],
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"OpenAlex returned HTTP {response.status_code}",
                    response=response,
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt >= retries:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
    raise RuntimeError("unreachable")


def sampled_authors(
    session: requests.Session,
    args: argparse.Namespace,
) -> Iterable[Dict[str, Any]]:
    pages = math.ceil(args.sample_authors / args.per_page)
    seen = set()
    for page in range(1, pages + 1):
        remaining = args.sample_authors - len(seen)
        if remaining <= 0:
            return
        data = request_json(
            session,
            AUTHORS_URL,
            {
                "filter": f"has_orcid:true,works_count:>{args.min_works - 1}",
                "sample": args.sample_authors,
                "seed": args.seed,
                "per-page": min(args.per_page, remaining),
                "page": page,
                "select": AUTHOR_SELECT,
            },
            args.timeout,
            args.retries,
        )
        for author in data.get("results") or []:
            author_id = short_openalex_id(author.get("id"))
            orcid = normalized_orcid(author.get("orcid"))
            if author_id and orcid and author_id not in seen:
                seen.add(author_id)
                yield author
        if args.sleep:
            time.sleep(args.sleep)


def target_authorship(work: Mapping[str, Any], author_id: str) -> Optional[Dict[str, Any]]:
    for authorship in work.get("authorships") or []:
        if short_openalex_id((authorship.get("author") or {}).get("id")) == author_id:
            return dict(authorship)
    return None


def author_works(
    session: requests.Session,
    author_id: str,
    args: argparse.Namespace,
) -> list[Dict[str, Any]]:
    data = request_json(
        session,
        WORKS_URL,
        {
            "filter": (
                f"author.id:{author_id},"
                f"from_publication_date:{args.from_year}-01-01,"
                f"to_publication_date:{args.to_year}-12-31"
            ),
            "sort": "publication_date:asc",
            "per-page": args.max_works,
            "select": SELECT_FIELDS,
        },
        args.timeout,
        args.retries,
    )
    return list(data.get("results") or [])


def target_mention(
    work: Mapping[str, Any],
    authorship: Mapping[str, Any],
    gold_orcid: str,
    source_author_id: str,
) -> Dict[str, Any]:
    name = author_name(authorship)
    family, given, split_source = split_display_name(name)
    all_names = [author_name(row) for row in work.get("authorships") or []]
    position = next(
        (
            index for index, row in enumerate(work.get("authorships") or [], start=1)
            if row is authorship or row == authorship
        ),
        1,
    )
    topic = work.get("primary_topic") or {}
    work_id = short_openalex_id(work.get("id"))
    return {
        "mention_id": f"{work_id}:{source_author_id}",
        "article_id": work_id,
        "doi": str(work.get("doi") or "").removeprefix("https://doi.org/"),
        "title": str(work.get("title") or ""),
        "year": work.get("publication_year"),
        "position": position,
        "gold_author_id": gold_orcid,
        "source_openalex_author_id": source_author_id,
        "name": name,
        "lastname": family,
        "firstname": given,
        "name_split_source": split_source,
        "orcid": "",
        "coauthors": [
            other for index, other in enumerate(all_names, start=1)
            if index != position and other and other != name
        ],
        "journal": source_name(work),
        "affiliation": first_affiliation(authorship),
        "field": str(((topic.get("field") or {}).get("display_name")) or ""),
        "domain": str(((topic.get("domain") or {}).get("display_name")) or ""),
        "source": "openalex_api_orcid_blind",
    }


def verified_author_mentions(
    author: Mapping[str, Any],
    args: argparse.Namespace,
) -> Optional[tuple[str, str, list[Dict[str, Any]]]]:
    author_id = short_openalex_id(author.get("id"))
    orcid = normalized_orcid(author.get("orcid"))
    session = requests.Session()
    if args.email:
        session.headers.update({"User-Agent": f"istina-author-research mailto:{args.email}"})
    works = []
    for work in author_works(session, author_id, args):
        authorship = target_authorship(work, author_id)
        embedded_orcid = normalized_orcid(
            ((authorship or {}).get("author") or {}).get("orcid")
        )
        if authorship and author_name(authorship) and embedded_orcid == orcid:
            works.append(target_mention(work, authorship, orcid, author_id))
    if len(works) < args.min_works:
        return None
    return author_id, orcid, works[:args.max_works]


def build(args: argparse.Namespace) -> Dict[str, Any]:
    session = requests.Session()
    if args.email:
        session.headers.update({"User-Agent": f"istina-author-research mailto:{args.email}"})
    accepted: list[tuple[str, str, list[Dict[str, Any]]]] = []
    seen_orcids = set()
    attempted = 0
    rejected_too_few = 0
    started = time.perf_counter()
    candidates = []
    candidate_orcids = set()
    for author in sampled_authors(session, args):
        orcid = normalized_orcid(author.get("orcid"))
        if orcid not in candidate_orcids:
            candidate_orcids.add(orcid)
            candidates.append(author)
    batch_size = max(args.workers, args.workers * 4)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for offset in range(0, len(candidates), batch_size):
            if len(accepted) >= args.target_authors:
                break
            batch = candidates[offset:offset + batch_size]
            for result in executor.map(
                lambda author: verified_author_mentions(author, args),
                batch,
            ):
                attempted += 1
                if result is None:
                    rejected_too_few += 1
                    continue
                _author_id, orcid, _works = result
                if orcid in seen_orcids:
                    continue
                seen_orcids.add(orcid)
                accepted.append(result)
                if len(accepted) >= args.target_authors:
                    break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    domain_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    name_variant_authors = 0
    mention_count = 0
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for _author_id, _orcid, mentions in accepted:
            if len({row["name"] for row in mentions}) > 1:
                name_variant_authors += 1
            for mention in mentions:
                handle.write(json.dumps(mention, ensure_ascii=False) + "\n")
                mention_count += 1
                domain_counts[mention["domain"] or "Unknown"] += 1
                field_counts[mention["field"] or "Unknown"] += 1

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "authors_url": AUTHORS_URL,
            "works_url": WORKS_URL,
            "documentation": "https://developers.openalex.org/",
            "openalex_paper_doi": "10.1038/s41597-022-01371-4",
            "orcid": "https://orcid.org/",
        },
        "request": {
            "target_authors": args.target_authors,
            "sample_authors": args.sample_authors,
            "seed": args.seed,
            "min_works": args.min_works,
            "max_works": args.max_works,
            "from_year": args.from_year,
            "to_year": args.to_year,
        },
        "counts": {
            "authors_attempted": attempted,
            "authors_accepted": len(accepted),
            "authors_rejected_too_few_verified_works": rejected_too_few,
            "mentions": mention_count,
            "authors_with_raw_name_variants": name_variant_authors,
        },
        "domain_counts": dict(domain_counts.most_common()),
        "field_counts": dict(field_counts.most_common()),
        "elapsed_seconds": time.perf_counter() - started,
        "gold_policy": (
            "ORCID used only as identity label; mention.orcid is blank and the "
            "runtime never receives ORCID"
        ),
        "output": str(args.output),
    }
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-authors", type=int, default=1500)
    parser.add_argument("--sample-authors", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--min-works", type=int, default=3)
    parser.add_argument("--max-works", type=int, default=5)
    parser.add_argument("--from-year", type=int, default=2000)
    parser.add_argument("--to-year", type=int, default=2025)
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.11)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--email")
    parser.add_argument("--output", type=Path, default=Path("data/openalex_orcid_mentions.jsonl"))
    parser.add_argument("--metadata", type=Path, default=Path("data/openalex_orcid_metadata.json"))
    args = parser.parse_args()
    if not 1 <= args.target_authors <= args.sample_authors <= 10_000:
        parser.error("require 1 <= target-authors <= sample-authors <= 10000")
    if not 2 <= args.min_works <= args.max_works <= 200:
        parser.error("require 2 <= min-works <= max-works <= 200")
    if not 1 <= args.workers <= 16:
        parser.error("workers must be within [1, 16]")
    print(json.dumps(build(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
