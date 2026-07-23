"""Run the official S2AND Python baseline on the frozen public replay.

This is a formal development benchmark, not a final blind test.  The runner
uses one official incremental call per name block, stores anonymous aggregate
contingencies in an atomic SQLite checkpoint, and emits only bounded progress
lines.  Query identities never enter the S2AND payload or history seeds.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stderr, redirect_stdout
import gc
import hashlib
import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path
import pickle
import sqlite3
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import sha256_file  # noqa: E402
from experiments.s2and_official_adapter import build_s2and_service_payload  # noqa: E402
from experiments.s2and_public_replay import (  # noqa: E402
    ReplayCorpus,
    ReplayMention,
    adapter_inputs,
    deterministic_query_blocks,
    load_replay_corpus,
)


CHECKPOINT_SCHEMA_VERSION = "project2_s2and_python_checkpoint_v1"
RESULT_SCHEMA_VERSION = "project2_s2and_python_public_baseline_v1"


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def wilson_interval_95(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    rate = successes / total
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    radius = (
        z
        * math.sqrt(rate * (1.0 - rate) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _identity_index(corpus: ReplayCorpus) -> tuple[dict[str, int], str]:
    identities = {
        mention.identity
        for history, query in corpus.blocks.values()
        for mention in (*history, *query)
    }
    ordered = sorted(
        identities,
        key=lambda identity: hashlib.sha256(identity.encode("utf-8")).digest(),
    )
    digests = [hashlib.sha256(identity.encode("utf-8")).hexdigest() for identity in ordered]
    partition_digest = hashlib.sha256("\n".join(digests).encode("ascii")).hexdigest()
    return {identity: index for index, identity in enumerate(ordered)}, partition_digest


def evaluate_block(
    *,
    block_ordinal: int,
    history_signature_ids: Sequence[str],
    query_signature_ids: Sequence[str],
    history_mentions: Sequence[ReplayMention],
    query_mentions: Sequence[ReplayMention],
    identity_index: Mapping[str, int],
    global_history_identity_indices: set[int],
    clusters: Mapping[Any, Sequence[str]],
    phase_b_mode: str,
    elapsed_seconds: float,
) -> dict[str, Any]:
    if len(history_signature_ids) != len(history_mentions):
        raise ValueError("history signature/label cardinality mismatch")
    if len(query_signature_ids) != len(query_mentions):
        raise ValueError("query signature/label cardinality mismatch")

    signature_cluster: dict[str, str] = {}
    cluster_members: dict[str, list[str]] = {}
    for cluster_id, raw_members in clusters.items():
        cluster_key = str(cluster_id)
        members = [str(member) for member in raw_members]
        cluster_members[cluster_key] = members
        for signature_id in members:
            if signature_id in signature_cluster:
                raise ValueError("signature assigned to multiple S2AND clusters")
            signature_cluster[signature_id] = cluster_key

    history_identity_by_signature = {
        signature_id: int(identity_index[mention.identity])
        for signature_id, mention in zip(
            history_signature_ids,
            history_mentions,
            strict=True,
        )
    }
    history_identities_by_cluster: dict[str, set[int]] = defaultdict(set)
    for signature_id, identity in history_identity_by_signature.items():
        cluster_key = signature_cluster.get(signature_id)
        if cluster_key is None:
            raise ValueError("history seed missing from S2AND result")
        history_identities_by_cluster[cluster_key].add(identity)

    query_cluster_keys = sorted(
        {signature_cluster.get(signature_id, "") for signature_id in query_signature_ids}
    )
    if "" in query_cluster_keys:
        raise ValueError("query signature missing from S2AND result")
    local_cluster_index = {
        cluster_key: index for index, cluster_key in enumerate(query_cluster_keys)
    }

    counts: Counter[str] = Counter()
    contingency: Counter[tuple[int, str]] = Counter()
    block_history_identities = set(history_identity_by_signature.values())
    for signature_id, mention in zip(query_signature_ids, query_mentions, strict=True):
        gold = int(identity_index[mention.identity])
        known = gold in global_history_identity_indices
        cluster_key = signature_cluster[signature_id]
        predicted_history = history_identities_by_cluster.get(cluster_key, set())
        linked = bool(predicted_history)
        correct = len(predicted_history) == 1 and gold in predicted_history

        counts["total"] += 1
        counts["known" if known else "new"] += 1
        counts["candidate_covered_known"] += int(known and gold in block_history_identities)
        counts["predicted_links"] += int(linked)
        counts["correct_known"] += int(known and correct)
        counts["wrong_known"] += int(known and linked and not correct)
        counts["known_nil"] += int(known and not linked)
        counts["false_links_new"] += int(not known and linked)
        counts["seed_conflict_queries"] += int(len(predicted_history) > 1)

        if len(predicted_history) == 1:
            predicted_token = f"existing:{next(iter(predicted_history))}"
        elif len(predicted_history) > 1:
            predicted_token = (
                f"conflict:{block_ordinal}:{local_cluster_index[cluster_key]}"
            )
        else:
            predicted_token = f"new:{block_ordinal}:{local_cluster_index[cluster_key]}"
        contingency[(gold, predicted_token)] += 1

    query_count = len(query_signature_ids)
    history_count = len(history_signature_ids)
    return {
        "counts": dict(counts),
        "contingency": [
            [gold, predicted, count]
            for (gold, predicted), count in sorted(
                contingency.items(), key=lambda item: (item[0][0], item[0][1])
            )
        ],
        "history": history_count,
        "query": query_count,
        "theoretical_pairs": (
            query_count * history_count + query_count * (query_count - 1) // 2
        ),
        "phase_b_mode": str(phase_b_mode),
        "elapsed_seconds": float(elapsed_seconds),
    }


def aggregate_block_payloads(payloads: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    cells: Counter[tuple[int, str]] = Counter()
    phase_modes: Counter[str] = Counter()
    elapsed = 0.0
    theoretical_pairs = 0
    blocks = 0
    for payload in payloads:
        blocks += 1
        totals.update({key: int(value) for key, value in payload["counts"].items()})
        for gold, predicted, count in payload["contingency"]:
            cells[(int(gold), str(predicted))] += int(count)
        phase_modes[str(payload["phase_b_mode"])] += 1
        elapsed += float(payload["elapsed_seconds"])
        theoretical_pairs += int(payload["theoretical_pairs"])

    gold_sizes: Counter[int] = Counter()
    predicted_sizes: Counter[str] = Counter()
    for (gold, predicted), count in cells.items():
        gold_sizes[gold] += count
        predicted_sizes[predicted] += count
    total_mentions = sum(cells.values())
    b3_precision_sum = sum(
        count * count / predicted_sizes[predicted]
        for (gold, predicted), count in cells.items()
    )
    b3_recall_sum = sum(
        count * count / gold_sizes[gold]
        for (gold, predicted), count in cells.items()
    )
    b3_precision = _ratio(b3_precision_sum, total_mentions)
    b3_recall = _ratio(b3_recall_sum, total_mentions)
    b3_f1 = _ratio(2.0 * b3_precision * b3_recall, b3_precision + b3_recall)

    true_pairs = sum(count * (count - 1) // 2 for count in cells.values())
    gold_pairs = sum(size * (size - 1) // 2 for size in gold_sizes.values())
    predicted_pairs = sum(size * (size - 1) // 2 for size in predicted_sizes.values())
    pair_precision = _ratio(true_pairs, predicted_pairs)
    pair_recall = _ratio(true_pairs, gold_pairs)
    pair_f1 = _ratio(2.0 * pair_precision * pair_recall, pair_precision + pair_recall)

    known_predictions = totals["correct_known"] + totals["wrong_known"]
    accepted_predictions = totals["predicted_links"]
    return {
        "counts": dict(totals),
        "linking": {
            "candidate_recall": _ratio(totals["candidate_covered_known"], totals["known"]),
            "known_recall": _ratio(totals["correct_known"], totals["known"]),
            "known_recall_ci95": wilson_interval_95(totals["correct_known"], totals["known"]),
            "known_prediction_precision": _ratio(totals["correct_known"], known_predictions),
            "known_prediction_precision_ci95": wilson_interval_95(
                totals["correct_known"], known_predictions
            ),
            "accepted_link_precision": _ratio(totals["correct_known"], accepted_predictions),
            "accepted_link_precision_ci95": wilson_interval_95(
                totals["correct_known"], accepted_predictions
            ),
            "wrong_known_rate": _ratio(totals["wrong_known"], totals["known"]),
            "wrong_known_rate_ci95": wilson_interval_95(totals["wrong_known"], totals["known"]),
            "new_author_false_link_rate": _ratio(totals["false_links_new"], totals["new"]),
            "new_author_false_link_rate_ci95": wilson_interval_95(
                totals["false_links_new"], totals["new"]
            ),
        },
        "clustering": {
            "b3": {
                "precision": b3_precision,
                "recall": b3_recall,
                "f1": b3_f1,
            },
            "pairwise": {
                "precision": pair_precision,
                "recall": pair_recall,
                "f1": pair_f1,
                "true_positive_pairs": true_pairs,
                "predicted_pairs": predicted_pairs,
                "gold_pairs": gold_pairs,
            },
        },
        "execution": {
            "completed_blocks": blocks,
            "phase_b_modes": dict(phase_modes),
            "block_inference_seconds": elapsed,
            "theoretical_pair_comparisons": theoretical_pairs,
        },
    }


class Checkpoint:
    def __init__(self, path: Path, manifest: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS block_results "
            "(ordinal INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        manifest_text = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        existing = self.connection.execute(
            "SELECT value FROM meta WHERE key='manifest'"
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO meta(key, value) VALUES('manifest', ?)",
                (manifest_text,),
            )
            self.connection.commit()
        elif existing[0] != manifest_text:
            self.connection.close()
            raise ValueError("checkpoint manifest does not match this frozen run")

    def completed(self) -> set[int]:
        return {
            int(row[0])
            for row in self.connection.execute("SELECT ordinal FROM block_results")
        }

    def put(self, ordinal: int, payload: Mapping[str, Any]) -> None:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self.connection:
            self.connection.execute(
                "INSERT INTO block_results(ordinal, payload) VALUES(?, ?)",
                (int(ordinal), text),
            )

    def payloads(self) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT payload FROM block_results ORDER BY ordinal"
            )
        ]

    def close(self) -> None:
        self.connection.close()


def _git_output(arguments: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={cwd.as_posix()}", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _run_manifest(
    *,
    authors_path: Path,
    article_authors_path: Path,
    enrichment_dir: Path,
    model_dir: Path | None,
    model_pickle: Path | None,
    s2and_repo: Path,
    cutoff_year: int,
    batch_blocks: int,
    selected_blocks: Sequence[str],
    corpus: ReplayCorpus,
    identity_partition_sha256: str,
) -> dict[str, Any]:
    dirty = _git_output(["status", "--porcelain", "--untracked-files=all"], PROJECT_ROOT)
    if dirty:
        raise RuntimeError("formal S2AND run requires a clean tracked worktree")
    enrichment_manifest = enrichment_dir / "aggregate_manifest.json"
    if (model_dir is None) == (model_pickle is None):
        raise ValueError("set exactly one of model_dir and model_pickle")
    if model_dir is not None:
        model_artifact = {
            "type": "official_production_bundle",
            "sha256": sha256_file(model_dir / "manifest.json"),
        }
    else:
        assert model_pickle is not None
        model_artifact = {
            "type": "stock_s2and_retrained_pickle",
            "sha256": sha256_file(model_pickle),
        }
        training_result = model_pickle.parent / "training_result.json"
        if training_result.is_file():
            model_artifact["training_result_sha256"] = sha256_file(training_result)
    manifest = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "development_only": True,
        "backend": "official_s2and_python_exact_incremental",
        "project_revision": _git_output(["rev-parse", "HEAD"], PROJECT_ROOT),
        "s2and_revision": _git_output(["rev-parse", "HEAD"], s2and_repo),
        "s2and_version": importlib.metadata.version("s2and"),
        "model_artifact": model_artifact,
        "authors_sha256": sha256_file(authors_path),
        "article_authors_sha256": sha256_file(article_authors_path),
        "enrichment_manifest_sha256": sha256_file(enrichment_manifest),
        "identity_partition_sha256": identity_partition_sha256,
        "cutoff_year": int(cutoff_year),
        "batch_blocks": int(batch_blocks),
        "selected_blocks": len(selected_blocks),
        "selected_history_authorships": sum(
            len(corpus.blocks[block][0]) for block in selected_blocks
        ),
        "selected_query_authorships": sum(
            len(corpus.blocks[block][1]) for block in selected_blocks
        ),
    }
    manifest["run_signature"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _observed_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.batch_blocks <= 0 or args.progress_every <= 0:
        raise ValueError("batch-blocks and progress-every must be positive")
    os.environ["S2AND_BACKEND"] = "python"
    os.environ["S2AND_CACHE"] = str(args.s2and_cache.resolve())
    os.environ["MPLCONFIGDIR"] = str((args.run_dir / "mpl-cache").resolve())
    os.environ["TQDM_DISABLE"] = "1"
    sys.path.insert(0, str(args.s2and_repo.resolve()))

    corpus = load_replay_corpus(
        args.authors,
        args.article_authors,
        args.enrichment_dir,
        cutoff_year=args.cutoff_year,
    )
    query_blocks = deterministic_query_blocks(corpus)
    if args.max_blocks > 0:
        query_blocks = query_blocks[:args.max_blocks]
    identity_index, identity_partition_sha256 = _identity_index(corpus)
    history_identity_indices = {
        identity_index[identity] for identity in corpus.global_history_identities
    }
    manifest = _run_manifest(
        authors_path=args.authors,
        article_authors_path=args.article_authors,
        enrichment_dir=args.enrichment_dir,
        model_dir=args.model_dir,
        model_pickle=args.model_pickle,
        s2and_repo=args.s2and_repo,
        cutoff_year=args.cutoff_year,
        batch_blocks=args.batch_blocks,
        selected_blocks=query_blocks,
        corpus=corpus,
        identity_partition_sha256=identity_partition_sha256,
    )
    args.run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(args.run_dir / "checkpoint.sqlite3", manifest)
    completed = checkpoint.completed()
    pending = [
        block for ordinal, block in enumerate(query_blocks) if ordinal not in completed
    ]
    print(
        "formal_s2and_start "
        f"blocks={len(query_blocks)} completed={len(completed)} "
        f"pending={len(pending)} queries={manifest['selected_query_authorships']}"
    )

    from s2and.data import ANDData
    from scripts.convert_to_arrow import _cluster_seeds_payload

    logging.getLogger("s2and").setLevel(logging.ERROR)
    sink = open(os.devnull, "w", encoding="utf-8")
    started = time.perf_counter()
    peak_rss = _observed_rss_bytes()
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            if args.model_pickle is not None:
                with args.model_pickle.open("rb") as handle:
                    clusterer = pickle.load(handle)
            else:
                from s2and.production_model import load_production_model

                clusterer = load_production_model(
                    args.model_dir,
                    require_incremental_linker=False,
                )
        block_to_ordinal = {block: ordinal for ordinal, block in enumerate(query_blocks)}
        for batch in _chunks(pending, args.batch_blocks):
            history_rows, query_rows, query_mentions, embeddings = adapter_inputs(
                corpus, batch
            )
            adapter = build_s2and_service_payload(
                history_rows,
                query_rows,
                paper_embeddings=embeddings,
            )
            with redirect_stdout(sink), redirect_stderr(sink):
                dataset = ANDData(
                    signatures=adapter.payload["signatures"],
                    papers=adapter.payload["papers"],
                    name=f"project2-public-{manifest['run_signature'][:12]}",
                    mode="inference",
                    clusters=None,
                    specter_embeddings=adapter.payload["paper_embeddings"],
                    cluster_seeds=_cluster_seeds_payload(adapter.payload),
                    altered_cluster_signatures=[],
                    n_jobs=1,
                    load_name_counts=True,
                    preprocess=True,
                    use_orcid_id=True,
                    use_sinonym_overwrite=False,
                    compute_reference_features=False,
                )
            full_seed_map = dict(dataset.cluster_seeds_require)
            history_offset = 0
            query_offset = 0
            query_label_offset = 0
            for block in batch:
                history_mentions, block_query_mentions = corpus.blocks[block]
                history_ids = adapter.history_signature_ids[
                    history_offset:history_offset + len(history_mentions)
                ]
                query_ids = adapter.query_signature_ids[
                    query_offset:query_offset + len(block_query_mentions)
                ]
                labels = query_mentions[
                    query_label_offset:query_label_offset + len(block_query_mentions)
                ]
                history_offset += len(history_mentions)
                query_offset += len(block_query_mentions)
                query_label_offset += len(block_query_mentions)
                scoped_seed_map = {
                    signature_id: full_seed_map[signature_id]
                    for signature_id in history_ids
                }
                dataset.cluster_seeds_require = scoped_seed_map
                dataset.max_seed_cluster_id = len(set(scoped_seed_map.values()))
                block_started = time.perf_counter()
                try:
                    with redirect_stdout(sink), redirect_stderr(sink):
                        prediction = clusterer.predict_incremental(
                            list(query_ids),
                            dataset,
                            batching_threshold=None,
                        )
                except Exception as exc:
                    message = str(exc).replace("\n", " ")[:300]
                    raise RuntimeError(
                        f"official S2AND failed at anonymous block ordinal "
                        f"{block_to_ordinal[block]}: {type(exc).__name__}: {message}"
                    ) from exc
                payload = evaluate_block(
                    block_ordinal=block_to_ordinal[block],
                    history_signature_ids=history_ids,
                    query_signature_ids=query_ids,
                    history_mentions=history_mentions,
                    query_mentions=labels,
                    identity_index=identity_index,
                    global_history_identity_indices=history_identity_indices,
                    clusters=prediction["clusters"],
                    phase_b_mode=str(prediction.get("phase_b_mode", "unknown")),
                    elapsed_seconds=time.perf_counter() - block_started,
                )
                checkpoint.put(block_to_ordinal[block], payload)
                completed.add(block_to_ordinal[block])
                peak_rss = max(peak_rss, _observed_rss_bytes())
                if len(completed) % args.progress_every == 0:
                    print(
                        "formal_s2and_progress "
                        f"completed={len(completed)}/{len(query_blocks)} "
                        f"rss_mb={round(peak_rss / (1024 * 1024), 1)}"
                    )
            dataset.cluster_seeds_require = full_seed_map
            del dataset, adapter, history_rows, query_rows, query_mentions, embeddings
            gc.collect()
    finally:
        sink.close()

    payloads = checkpoint.payloads()
    aggregate = aggregate_block_payloads(payloads)
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "contains_record_values": False,
        "development_only": True,
        "complete": len(payloads) == len(query_blocks),
        "manifest": manifest,
        "metrics": aggregate,
        "clustering_scope": "query authorships only; existing links unify through history identity",
        "runtime": {
            "wall_seconds_this_invocation": time.perf_counter() - started,
            "observed_peak_rss_bytes": peak_rss,
            "checkpoint_blocks": len(payloads),
        },
    }
    _atomic_json(args.run_dir / "aggregate_result.json", result)
    checkpoint.close()
    print(
        "formal_s2and_complete "
        f"blocks={len(payloads)} queries={aggregate['counts'].get('total', 0)} "
        f"known_recall={aggregate['linking']['known_recall']:.6f} "
        f"new_false_link={aggregate['linking']['new_author_false_link_rate']:.6f}"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--s2and-repo", type=Path, required=True)
    model_group = parser.add_mutually_exclusive_group(required=True)
    model_group.add_argument("--model-dir", type=Path)
    model_group.add_argument("--model-pickle", type=Path)
    parser.add_argument("--s2and-cache", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, default=2021)
    parser.add_argument("--batch-blocks", type=int, default=64)
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--max-blocks", type=int, default=0)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
