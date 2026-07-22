"""Audit the paper-grade public subset after Semantic Scholar enrichment.

All identity values remain in memory as label-only grouping keys.  The report
contains aggregate counts and temporal split sizes only; it never emits a DOI,
ORCID, name, title, or embedding.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import iter_json_records, sha256_file  # noqa: E402
from experiments.semantic_scholar_specter_enrichment import (  # noqa: E402
    _read_cache,
    normalize_doi,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def load_enrichment_signals(cache_dir: Path) -> dict[str, set[str]]:
    signals = {
        "matched": set(),
        "title": set(),
        "abstract": set(),
        "venue": set(),
        "authors": set(),
        "specter2": set(),
    }
    seen_digests: set[str] = set()
    paths = sorted(cache_dir.glob("batch_*.json.gz")) + sorted(
        cache_dir.glob("batch_*.json")
    )
    for path in paths:
        cache = _read_cache(path)
        digest = _text(cache.get("doi_digest"))
        if not digest or digest in seen_digests:
            continue
        seen_digests.add(digest)
        rows = cache.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"invalid enrichment rows in {path.name}")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            external_ids = row.get("externalIds")
            if not isinstance(external_ids, Mapping):
                continue
            doi = normalize_doi(external_ids.get("DOI"))
            if not doi:
                continue
            signals["matched"].add(doi)
            if row.get("title"):
                signals["title"].add(doi)
            if row.get("abstract"):
                signals["abstract"].add(doi)
            if row.get("venue") or row.get("journal") or row.get("publicationVenue"):
                signals["venue"].add(doi)
            if row.get("authors"):
                signals["authors"].add(doi)
            embedding = row.get("embedding")
            vector = embedding.get("vector") if isinstance(embedding, Mapping) else None
            if isinstance(vector, list) and len(vector) == 768:
                signals["specter2"].add(doi)
    return signals


def _temporal_stats(
    mentions: list[tuple[str, str, int]],
    cutoff: int,
) -> dict[str, int]:
    history = [mention for mention in mentions if mention[2] <= cutoff]
    query = [mention for mention in mentions if mention[2] > cutoff]
    history_identities = {identity for _doi, identity, _year in history}
    known_query = [mention for mention in query if mention[1] in history_identities]
    new_query = [mention for mention in query if mention[1] not in history_identities]
    return {
        "cutoff_year": cutoff,
        "history_authorships": len(history),
        "history_identities": len(history_identities),
        "query_authorships": len(query),
        "known_query_authorships": len(known_query),
        "new_query_authorships": len(new_query),
        "known_query_identities": len({mention[1] for mention in known_query}),
        "new_query_identities": len({mention[1] for mention in new_query}),
        "query_papers": len({mention[0] for mention in query}),
    }


def build_report(authors_path: Path, cache_dir: Path) -> dict[str, Any]:
    signals = load_enrichment_signals(cache_dir)
    specter_dois = signals["specter2"]
    base_usable = 0
    matched_usable = 0
    specter_usable = 0
    mentions: list[tuple[str, str, int]] = []
    identity_mentions: Counter[str] = Counter()
    identity_papers: dict[str, set[str]] = defaultdict(set)
    year_counts: Counter[int] = Counter()
    specter_papers: set[str] = set()

    with authors_path.open("r", encoding="utf-8-sig") as handle:
        for row in iter_json_records(handle):
            if not isinstance(row, Mapping):
                continue
            first = _text(row.get("firstname"))
            last = _text(row.get("lastname"))
            identity = _text(row.get("orcid"))
            doi = normalize_doi(row.get("doi"))
            try:
                year = int(row.get("year"))
            except (TypeError, ValueError):
                continue
            if not first or not last or not identity or not doi:
                continue
            base_usable += 1
            if doi in signals["matched"]:
                matched_usable += 1
            if doi not in specter_dois:
                continue
            specter_usable += 1
            specter_papers.add(doi)
            mentions.append((doi, identity, year))
            identity_mentions[identity] += 1
            identity_papers[identity].add(doi)
            year_counts[year] += 1

    repeated_identities = {
        identity for identity, papers in identity_papers.items() if len(papers) >= 2
    }
    return {
        "schema_version": "project2_s2and_ready_subset_v1",
        "contains_record_values": False,
        "source": {
            "authors_file": authors_path.name,
            "authors_sha256": sha256_file(authors_path),
            "enrichment_manifest": "aggregate_manifest.json",
        },
        "paper_signals": {key: len(values) for key, values in sorted(signals.items())},
        "authorships": {
            "structured_label_year_doi": base_usable,
            "semantic_scholar_matched": matched_usable,
            "s2and_complete_specter2_subset": specter_usable,
            "distinct_papers": len(specter_papers),
            "distinct_identities": len(identity_mentions),
            "repeated_identities": len(repeated_identities),
            "authorships_of_repeated_identities": sum(
                identity_mentions[identity] for identity in repeated_identities
            ),
            "identities_with_at_least_3_papers": sum(
                len(papers) >= 3 for papers in identity_papers.values()
            ),
        },
        "year_authorship_counts": {
            str(year): count for year, count in sorted(year_counts.items())
        },
        "temporal_splits": {
            str(cutoff): _temporal_stats(mentions, cutoff)
            for cutoff in (2020, 2021, 2022)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args.authors, args.cache_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    authorships = report["authorships"]
    print(
        "s2and_ready_subset "
        f"authorships={authorships['s2and_complete_specter2_subset']} "
        f"papers={authorships['distinct_papers']} "
        f"identities={authorships['distinct_identities']} "
        f"repeated={authorships['repeated_identities']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
