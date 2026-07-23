"""Audit block coverage and exact-pair cost for the public S2AND replay.

The Crossref--ORCID identity is used only as an in-memory evaluation label.
The report contains aggregate counts and never emits a name, DOI, ORCID, or
paper value.  Semantic Scholar cache rows are reduced to the set of DOIs with
real 768-dimensional SPECTER2 vectors before the author export is scanned.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import iter_json_records, sha256_file  # noqa: E402
from experiments.audit_s2and_ready_subset import load_enrichment_signals  # noqa: E402
from experiments.semantic_scholar_specter_enrichment import normalize_doi  # noqa: E402


def _text(value: Any) -> str:
    return str(value or "").strip()


def canonical_block(first: str, last: str) -> str:
    """Match the explicit blocking key used by the Project Two S2AND adapter."""

    normalized_first = unicodedata.normalize("NFKC", first).strip().casefold()
    normalized_last = " ".join(
        unicodedata.normalize("NFKC", last).strip().casefold().split()
    )
    if not normalized_first or not normalized_last:
        raise ValueError("structured first and last name are required")
    return normalized_first[0] + " " + normalized_last


def _nearest_rank(values: Iterable[int], probability: float) -> int:
    ordered = sorted(int(value) for value in values)
    if not ordered:
        return 0
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def _distribution(values: Iterable[int]) -> dict[str, int]:
    materialized = list(values)
    return {
        "p50": _nearest_rank(materialized, 0.50),
        "p90": _nearest_rank(materialized, 0.90),
        "p95": _nearest_rank(materialized, 0.95),
        "p99": _nearest_rank(materialized, 0.99),
        "max": max(materialized, default=0),
    }


def build_report(
    authors_path: Path,
    cache_dir: Path,
    *,
    cutoff_year: int,
) -> dict[str, Any]:
    specter_dois = load_enrichment_signals(cache_dir)["specter2"]
    history_by_block: Counter[str] = Counter()
    query_by_block: Counter[str] = Counter()
    history_identities_by_block: dict[str, set[str]] = defaultdict(set)
    global_history_identities: set[str] = set()
    query_mentions: list[tuple[str, str]] = []
    paper_sides: dict[str, int] = {}
    conflicting_papers: set[str] = set()
    eligible = 0

    with authors_path.open("r", encoding="utf-8-sig") as handle:
        for raw in iter_json_records(handle):
            if not isinstance(raw, Mapping):
                continue
            # Whitelist reconstruction: the synthetic original_name field is
            # deliberately neither accessed nor copied past this boundary.
            first = _text(raw.get("firstname"))
            last = _text(raw.get("lastname"))
            identity = _text(raw.get("orcid"))
            doi = normalize_doi(raw.get("doi"))
            try:
                year = int(raw.get("year"))
            except (TypeError, ValueError):
                continue
            if not first or not last or not identity or not doi or doi not in specter_dois:
                continue

            block = canonical_block(first, last)
            side = 0 if year <= cutoff_year else 1
            previous_side = paper_sides.setdefault(doi, side)
            if previous_side != side:
                conflicting_papers.add(doi)
            eligible += 1
            if side == 0:
                history_by_block[block] += 1
                history_identities_by_block[block].add(identity)
                global_history_identities.add(identity)
            else:
                query_by_block[block] += 1
                query_mentions.append((block, identity))

    if conflicting_papers:
        raise ValueError(
            f"temporal paper leakage detected for {len(conflicting_papers)} paper(s)"
        )

    query_known = 0
    query_new = 0
    known_covered_by_block = 0
    for block, identity in query_mentions:
        if identity in global_history_identities:
            query_known += 1
            known_covered_by_block += int(identity in history_identities_by_block[block])
        else:
            query_new += 1

    blocks = set(history_by_block).union(query_by_block)
    query_blocks = {block for block in blocks if query_by_block[block]}
    exact_pairs = {
        block: (
            query_by_block[block] * history_by_block[block]
            + query_by_block[block] * (query_by_block[block] - 1) // 2
        )
        for block in query_blocks
    }
    block_sizes = {
        block: history_by_block[block] + query_by_block[block]
        for block in query_blocks
    }
    total_exact_pairs = sum(exact_pairs.values())
    return {
        "schema_version": "project2_s2and_replay_complexity_v1",
        "contains_record_values": False,
        "source": {
            "authors_file": authors_path.name,
            "authors_sha256": sha256_file(authors_path),
            "cutoff_year": cutoff_year,
            "specter2_papers": len(specter_dois),
        },
        "authorships": {
            "eligible": eligible,
            "history": sum(history_by_block.values()),
            "query": len(query_mentions),
            "known_query": query_known,
            "new_query": query_new,
            "known_query_covered_by_exact_block": known_covered_by_block,
            "known_query_missed_by_exact_block": query_known - known_covered_by_block,
        },
        "blocks": {
            "all": len(blocks),
            "with_query": len(query_blocks),
            "with_history_and_query": sum(
                bool(history_by_block[block]) for block in query_blocks
            ),
            "query_without_history": sum(
                not history_by_block[block] for block in query_blocks
            ),
            "size_distribution": _distribution(block_sizes.values()),
            "history_distribution": _distribution(
                history_by_block[block] for block in query_blocks
            ),
            "query_distribution": _distribution(
                query_by_block[block] for block in query_blocks
            ),
            "blocks_over_size": {
                str(threshold): sum(size > threshold for size in block_sizes.values())
                for threshold in (100, 500, 1_000, 5_000)
            },
        },
        "python_exact_incremental_cost": {
            "formula": "query*history + query*(query-1)/2 per block",
            "total_pair_comparisons": total_exact_pairs,
            "pair_distribution": _distribution(exact_pairs.values()),
            "blocks_over_pairs": {
                str(threshold): sum(pairs > threshold for pairs in exact_pairs.values())
                for threshold in (100_000, 1_000_000, 10_000_000)
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, default=2021)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        args.authors,
        args.cache_dir,
        cutoff_year=args.cutoff_year,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    authorships = report["authorships"]
    cost = report["python_exact_incremental_cost"]
    print(
        "s2and_replay_complexity "
        f"query={authorships['query']} "
        f"known_block_covered={authorships['known_query_covered_by_exact_block']} "
        f"pairs={cost['total_pair_comparisons']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
