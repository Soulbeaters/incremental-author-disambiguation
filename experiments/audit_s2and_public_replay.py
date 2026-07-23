"""Build the leakage-safe public replay and emit aggregate join coverage only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import sha256_file  # noqa: E402
from experiments.s2and_public_replay import load_replay_corpus  # noqa: E402


def build_report(
    authors_path: Path,
    article_authors_path: Path,
    cache_dir: Path,
    *,
    cutoff_year: int,
) -> dict[str, Any]:
    corpus = load_replay_corpus(
        authors_path,
        article_authors_path,
        cache_dir,
        cutoff_year=cutoff_year,
    )
    known = 0
    new = 0
    block_covered = 0
    for history, query in corpus.blocks.values():
        block_history = {mention.identity for mention in history}
        for mention in query:
            if mention.identity in corpus.global_history_identities:
                known += 1
                block_covered += int(mention.identity in block_history)
            else:
                new += 1
    return {
        "schema_version": "project2_s2and_public_replay_join_v1",
        "contains_record_values": False,
        "source": {
            "authors_file": authors_path.name,
            "authors_sha256": sha256_file(authors_path),
            "article_authors_file": article_authors_path.name,
            "article_authors_sha256": sha256_file(article_authors_path),
            "cutoff_year": cutoff_year,
        },
        "coverage": corpus.coverage,
        "replay": {
            "history_authorships": corpus.history_count,
            "query_authorships": corpus.query_count,
            "known_query": known,
            "new_query": new,
            "known_query_covered_by_block": block_covered,
            "known_query_missed_by_block": known - block_covered,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, default=2021)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        args.authors,
        args.article_authors,
        args.cache_dir,
        cutoff_year=args.cutoff_year,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    replay = report["replay"]
    print(
        "s2and_public_replay_join "
        f"history={replay['history_authorships']} "
        f"query={replay['query_authorships']} "
        f"known={replay['known_query']} "
        f"new={replay['new_query']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
