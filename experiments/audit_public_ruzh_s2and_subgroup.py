"""Aggregate official-S2AND outcomes for the public RuZh name stratum.

The official v1 checkpoint intentionally stores anonymous block-level
contingencies rather than query records.  This audit reconstructs the frozen
deterministic block order, selects blocks whose query mentions are all in the
Russian-script / Chinese-name processing stratum, and aggregates only their
anonymous contingencies.  It never reruns S2AND and never writes record values.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from disambiguation_engine.ruzh_name_evidence import name_evidence
from experiments.run_s2and_official_public_baseline import (
    aggregate_block_payloads,
)
from experiments.s2and_public_replay import (
    deterministic_query_blocks,
    load_replay_corpus,
)


SCHEMA_VERSION = "project2_public_ruzh_s2and_subgroup_v1"


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    official = json.loads(args.official_result.read_text(encoding="utf-8"))
    if not official.get("complete"):
        raise ValueError("official S2AND result is incomplete")
    corpus = load_replay_corpus(
        args.authors,
        args.article_authors,
        args.enrichment_dir,
        cutoff_year=args.cutoff_year,
    )
    blocks = deterministic_query_blocks(corpus)
    if len(blocks) != int(official["manifest"]["selected_blocks"]):
        raise ValueError("reconstructed block count differs from official run")

    connection = sqlite3.connect(f"file:{args.checkpoint}?mode=ro", uri=True)
    try:
        manifest_row = connection.execute(
            "SELECT value FROM meta WHERE key='manifest'"
        ).fetchone()
        if manifest_row is None:
            raise ValueError("checkpoint manifest is missing")
        checkpoint_manifest = json.loads(manifest_row[0])
        if (
            checkpoint_manifest.get("run_signature")
            != official["manifest"].get("run_signature")
        ):
            raise ValueError("checkpoint and official result signatures differ")
        payload_by_ordinal = {
            int(ordinal): json.loads(payload)
            for ordinal, payload in connection.execute(
                "SELECT ordinal, payload FROM block_results ORDER BY ordinal"
            )
        }
    finally:
        connection.close()
    if len(payload_by_ordinal) != len(blocks):
        raise ValueError("checkpoint does not contain every frozen block")

    selected_payloads = []
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for ordinal, block in enumerate(blocks):
        _history, queries = corpus.blocks[block]
        target_flags = []
        block_reasons: Counter[str] = Counter()
        for query in queries:
            evidence = name_evidence(query.first, "", query.last)
            target_flags.append(evidence.target)
            if evidence.target:
                block_reasons.update(evidence.reasons)
        if target_flags and all(target_flags):
            selected_payloads.append(payload_by_ordinal[ordinal])
            counts["target_blocks"] += 1
            counts["target_queries"] += len(queries)
            reasons.update(block_reasons)
        elif any(target_flags):
            counts["mixed_blocks_excluded"] += 1
            counts["mixed_queries_excluded"] += len(queries)
        else:
            counts["non_target_blocks"] += 1
            counts["non_target_queries"] += len(queries)

    metrics = aggregate_block_payloads(selected_payloads)
    if metrics["counts"].get("total", 0) != counts["target_queries"]:
        raise AssertionError("target query count does not match contingencies")
    report = {
        "schema_version": SCHEMA_VERSION,
        "development_only": True,
        "contains_record_values": False,
        "official_run_signature": official["manifest"]["run_signature"],
        "cutoff_year": int(args.cutoff_year),
        "selection": dict(counts),
        "target_reasons": dict(sorted(reasons.items())),
        "metrics": metrics,
    }
    _atomic_json(args.output, report)
    print(
        "public_ruzh_s2and_subgroup "
        f"queries={counts['target_queries']} "
        f"known_recall={metrics['linking']['known_recall']:.6f} "
        "new_false_link="
        f"{metrics['linking']['new_author_false_link_rate']:.6f}"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--official-result", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
