"""Evaluate Project Two on the exact public replay used by official S2AND.

Temporal roles are moved strictly before the comparison window: history
through 2019 plus 2020 queries fit the ranker/NIL gate; 2021 papers select and
check the fixed threshold; history through 2021 plus all 2022+ queries form the
development comparison.  Query labels are evaluator-only and never enter
candidate features or the pipeline's whitelisted mention payload.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.paper_graph_rescue import HistoricalCoauthorGraph  # noqa: E402
from experiments.audit_crossref_s2and_coverage import sha256_file  # noqa: E402
from experiments.compare_core_with_istina_proxy import (  # noqa: E402
    native_graph_records,
    project2_config,
)
from experiments.evaluate_listwise_graph_gate import (  # noqa: E402
    aggregate_method,
    base_predictions,
    fixed_decision_risk_certificate,
    native_predictions,
    paired_binary,
    peak_working_set_bytes,
)
from experiments.grouped_candidate_ranker import (  # noqa: E402
    GATE_FEATURE_NAMES,
    RANKER_FEATURE_GROUPS,
    RANKER_FEATURE_NAMES,
    build_candidate_groups,
    fit_nil_gate,
    fit_ranker,
    gate_feature_indices,
    gate_scores,
    model_summary,
    out_of_fold_ranked_decisions,
    rank_groups,
    ranking_metrics,
    select_risk_bounded_threshold,
    threshold_predictions,
)
from experiments.istina_runtime_replay import (  # noqa: E402
    evaluate,
    merge_evaluation_results,
)
from experiments.s2and_public_replay import (  # noqa: E402
    ReplayCorpus,
    ReplayMention,
    load_replay_corpus,
)
from integrations.istina_pipeline import IstinaDisambiguationPipeline  # noqa: E402


SCHEMA_VERSION = "project2_same_s2and_public_replay_v2"
CHECKPOINT_SCHEMA_VERSION = "project2_replay_checkpoint_v1"


def _stable_key(mention: ReplayMention) -> tuple[int, bytes, int]:
    digest = hashlib.sha256(
        f"{mention.doi}\0{mention.identity}\0{mention.author_position}".encode("utf-8")
    ).digest()
    return mention.year, digest, mention.author_position


def all_mentions(corpus: ReplayCorpus) -> list[ReplayMention]:
    rows = [
        mention
        for history, query in corpus.blocks.values()
        for mention in (*history, *query)
    ]
    return sorted(rows, key=_stable_key)


def _project2_mention(mention: ReplayMention, article_index: int) -> dict[str, Any]:
    coauthors = [
        author.display_name
        for position, author in enumerate(mention.paper_authors)
        if position != mention.author_position
    ]
    return {
        "article_index": article_index,
        "article_id": mention.doi,
        "position": mention.author_position,
        "year": mention.year,
        "gold_author_id": mention.identity,
        "name": " ".join((mention.last, mention.first)),
        "lastname": mention.last,
        "firstname": mention.first,
        "middlename": "",
        "coauthors": coauthors,
        "journal": mention.paper.journal_name or mention.paper.venue,
        "affiliation": mention.affiliation,
        "title": mention.paper.title,
        "abstract": mention.paper.abstract,
        "paper_embedding": mention.paper.embedding,
    }


def _paper_bucket(doi: str, modulus: int) -> int:
    digest = hashlib.sha256(doi.casefold().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def _filter_mentions(
    mentions: Sequence[ReplayMention],
    *,
    through_year: int | None = None,
    from_year: int | None = None,
    exact_year: int | None = None,
    paper_bucket_modulus: int | None = None,
    paper_bucket: int | None = None,
    invert_bucket: bool = False,
) -> list[ReplayMention]:
    output = []
    for mention in mentions:
        if through_year is not None and mention.year > through_year:
            continue
        if from_year is not None and mention.year < from_year:
            continue
        if exact_year is not None and mention.year != exact_year:
            continue
        if paper_bucket_modulus is not None:
            selected = _paper_bucket(mention.doi, paper_bucket_modulus) == paper_bucket
            if selected == invert_bucket:
                continue
        output.append(mention)
    return output


def _mention_fingerprint(mentions: Sequence[ReplayMention]) -> str:
    digest = hashlib.sha256()
    for mention in mentions:
        digest.update(
            (
                f"{mention.doi}\0{mention.identity}\0{mention.author_position}"
                f"\0{mention.year}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _runtime_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for distribution in ("Levenshtein", "lightgbm", "numpy", "scikit-learn"):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            versions[distribution] = "missing"
    return versions


class ReplayCheckpoint:
    """Local ignored checkpoints for bounded, resumable formal replay."""

    def __init__(
        self,
        root: Path,
        *,
        signature: str,
        manifest: Mapping[str, Any],
        batch_size: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("checkpoint batch size must be positive")
        self.root = root
        self.signature = signature
        self.batch_size = batch_size
        self.root.mkdir(parents=True, exist_ok=True)
        expected_manifest = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "signature": signature,
            "batch_size": batch_size,
            "contains_record_values": False,
            "protocol": dict(manifest),
        }
        manifest_path = self.root / "manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing != expected_manifest:
                raise RuntimeError(
                    "checkpoint manifest differs from the current code, data, or protocol"
                )
        else:
            _atomic_json(manifest_path, expected_manifest)

        self.progress_path = self.root / "progress.json"
        if self.progress_path.exists():
            self.progress = json.loads(
                self.progress_path.read_text(encoding="utf-8")
            )
            if self.progress.get("signature") != signature:
                raise RuntimeError("checkpoint progress signature mismatch")
        else:
            self.progress = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "signature": signature,
                "contains_record_values": False,
                "status": "running",
                "phases": {},
            }
            self._save_progress()

    def _save_progress(self) -> None:
        _atomic_json(self.progress_path, self.progress)

    def mark_started(
        self,
        phase: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        state = self.progress["phases"].setdefault(phase, {})
        state["status"] = "running"
        state["attempts"] = int(state.get("attempts") or 0) + 1
        state["last_started_unix"] = time.time()
        if details:
            state.update(dict(details))
        self._save_progress()

    def mark_completed(
        self,
        phase: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        state = self.progress["phases"].setdefault(phase, {})
        started = float(state.get("last_started_unix") or time.time())
        state["status"] = "complete"
        state["last_completed_unix"] = time.time()
        state["last_wall_seconds"] = max(0.0, time.time() - started)
        if details:
            state.update(dict(details))
        self._save_progress()

    def evaluate_batches(
        self,
        phase: str,
        pipeline: IstinaDisambiguationPipeline,
        test_mentions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        total_batches = (
            (len(test_mentions) + self.batch_size - 1) // self.batch_size
            if test_mentions else 0
        )
        self.mark_started(
            phase,
            {
                "total_mentions": len(test_mentions),
                "total_batches": total_batches,
                "batch_size": self.batch_size,
            },
        )
        phase_dir = self.root / phase
        phase_dir.mkdir(parents=True, exist_ok=True)
        results: list[Mapping[str, Any]] = []
        reused_batches = 0
        completed_mentions = 0
        evaluation_seconds = 0.0

        for start in range(0, len(test_mentions), self.batch_size):
            end = min(len(test_mentions), start + self.batch_size)
            batch_mentions = test_mentions[start:end]
            mention_hash = _mapping_mention_fingerprint(batch_mentions)
            batch_path = phase_dir / f"batch_{start:08d}_{end:08d}.json"
            if batch_path.exists():
                payload = json.loads(batch_path.read_text(encoding="utf-8"))
                expected = {
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "signature": self.signature,
                    "phase": phase,
                    "start": start,
                    "end": end,
                    "mention_sha256": mention_hash,
                }
                observed = {key: payload.get(key) for key in expected}
                if observed != expected:
                    raise RuntimeError(f"invalid replay checkpoint batch: {batch_path}")
                result = payload["result"]
                reused_batches += 1
            else:
                result = evaluate(pipeline, list(batch_mentions), {})
                _atomic_compact_json(
                    batch_path,
                    {
                        "schema_version": CHECKPOINT_SCHEMA_VERSION,
                        "signature": self.signature,
                        "phase": phase,
                        "start": start,
                        "end": end,
                        "mention_sha256": mention_hash,
                        "contains_record_values": True,
                        "result": result,
                    },
                )
            results.append(result)
            completed_mentions += end - start
            evaluation_seconds += float(result.get("elapsed_seconds") or 0.0)
            state = self.progress["phases"][phase]
            state.update({
                "completed_batches": len(results),
                "completed_mentions": completed_mentions,
                "reused_batches": reused_batches,
                "evaluation_seconds": evaluation_seconds,
            })
            self._save_progress()

        merged = merge_evaluation_results(results)
        self.mark_completed(
            phase,
            {
                "completed_batches": len(results),
                "completed_mentions": completed_mentions,
                "reused_batches": reused_batches,
                "evaluation_seconds": evaluation_seconds,
            },
        )
        return merged

    def public_summary(self) -> dict[str, Any]:
        phases = {}
        for name, state in self.progress["phases"].items():
            phases[name] = {
                key: value
                for key, value in state.items()
                if key not in {"last_started_unix", "last_completed_unix"}
            }
        return {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "signature": self.signature,
            "batch_size": self.batch_size,
            "phases": phases,
        }

    def mark_run_complete(self) -> None:
        self.progress["status"] = "complete"
        self._save_progress()


def _mapping_mention_fingerprint(
    mentions: Sequence[Mapping[str, Any]],
) -> str:
    digest = hashlib.sha256()
    for mention in mentions:
        digest.update(
            (
                f"{mention.get('article_id')}\0{mention.get('gold_author_id')}"
                f"\0{mention.get('position')}\0{mention.get('year')}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def build_project2_replay(
    history_mentions: Sequence[ReplayMention],
    query_mentions: Sequence[ReplayMention],
    *,
    calibrated_candidate_threshold: float,
    checkpoint: ReplayCheckpoint | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    history = [
        _project2_mention(mention, index + 1)
        for index, mention in enumerate(history_mentions)
    ]
    test = [
        _project2_mention(mention, index + 1)
        for index, mention in enumerate(query_mentions)
    ]
    history_papers = {row["article_id"] for row in history}
    query_papers = {row["article_id"] for row in test}
    if history_papers.intersection(query_papers):
        raise ValueError("Project Two replay contains cross-role paper leakage")
    pipeline_phase = f"{phase}.pipeline" if phase else ""
    if checkpoint:
        checkpoint.mark_started(
            pipeline_phase,
            {"history_mentions": len(history)},
        )
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=project2_config(
            enable_calibrated_candidate_rescue=True,
            calibrated_candidate_threshold=calibrated_candidate_threshold,
        ),
        index_aliases=True,
    )
    if checkpoint:
        checkpoint.mark_completed(pipeline_phase)
        project2 = checkpoint.evaluate_batches(
            f"{phase}.evaluate",
            pipeline,
            test,
        )
        checkpoint.mark_started(
            f"{phase}.graph",
            {
                "history_mentions": len(history),
                "query_mentions": len(test),
            },
        )
    else:
        project2 = evaluate(pipeline, test, {})
    test_positions = list(range(len(test)))
    historical_graph = HistoricalCoauthorGraph.from_mentions(history)
    native = native_graph_records(
        history,
        project2["records"],
        test,
        test_positions,
        pipeline.history_state.repair_profiles,
        historical_graph=historical_graph,
    )
    if checkpoint:
        checkpoint.mark_completed(f"{phase}.graph")
    return {
        "history_mentions": len(history),
        "test_mentions": len(test),
        "project2": project2,
        "native": native,
        "profile_sizes": historical_graph.profile_sizes,
        "history_mentions_raw": history,
        "test_mentions_raw": test,
    }


def _trial_counts(replay: Mapping[str, Any]) -> tuple[int, int]:
    records = replay["project2"]["records"]
    known = sum(bool(record.get("gold_seen_in_history")) for record in records)
    return known, len(records) - known


def _risk_certificate(
    replay: Mapping[str, Any],
    predictions: Sequence[str | None],
    *,
    confidence: float,
    max_new_false_rate: float,
    max_wrong_known_rate: float,
) -> dict[str, Any]:
    result = fixed_decision_risk_certificate(
        replay,
        predictions,
        confidence=confidence,
        max_unseen_false_rate=max_new_false_rate,
        max_wrong_known_rate=max_wrong_known_rate,
    )
    result["label_status"] = "opened_public_development"
    result["statistical_risk_passed"] = result["eligible_for_promotion"]
    result["eligible_for_promotion"] = False
    return result


def _git_output(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={PROJECT_ROOT.as_posix()}", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_compact_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        handle.write("\n")
    os.replace(temporary, path)


def _compact_replay(replay: Mapping[str, Any]) -> dict[str, Any]:
    project2 = replay["project2"]
    return {
        "history_mentions": replay["history_mentions"],
        "test_mentions": replay["test_mentions"],
        "stats": project2["stats"],
        "candidate_retrieval": project2["candidate_retrieval"],
        "stage_counts": project2["stage_counts"],
        "elapsed_seconds": project2["elapsed_seconds"],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if _git_output(["status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("formal Project Two comparison requires a clean worktree")
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    project_revision = _git_output(["rev-parse", "HEAD"])
    input_hashes = {
        "authors_sha256": sha256_file(args.authors),
        "article_authors_sha256": sha256_file(args.article_authors),
        "enrichment_manifest_sha256": sha256_file(
            args.enrichment_dir / "aggregate_manifest.json"
        ),
        "s2and_aggregate_sha256": sha256_file(args.s2and_result),
    }
    checkpoint_protocol = {
        "project_revision": project_revision,
        **input_hashes,
        "runtime_versions": _runtime_versions(),
        "cutoff_year": 2021,
        "oof_folds": args.oof_folds,
        "validation_modulus": args.validation_modulus,
        "ranker_feature_group": args.ranker_feature_group,
        "confidence": args.confidence,
        "max_new_false_rate": args.max_new_false_rate,
        "max_wrong_known_rate": args.max_wrong_known_rate,
        "calibrated_candidate_threshold": args.calibrated_candidate_threshold,
    }
    checkpoint_signature = hashlib.sha256(
        json.dumps(
            checkpoint_protocol,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    checkpoint_root = args.checkpoint_dir or (
        args.output.parent / f"{args.output.stem}.checkpoints"
    )
    checkpoint = ReplayCheckpoint(
        checkpoint_root,
        signature=checkpoint_signature,
        manifest=checkpoint_protocol,
        batch_size=args.checkpoint_batch_size,
    )
    checkpoint.mark_started("corpus.load")
    corpus = load_replay_corpus(
        args.authors,
        args.article_authors,
        args.enrichment_dir,
        cutoff_year=2021,
    )
    mentions = all_mentions(corpus)
    year_counts = Counter(mention.year for mention in mentions)
    checkpoint.mark_completed(
        "corpus.load",
        {
            "mentions": len(mentions),
            "blocks": len(corpus.blocks),
            "mentions_sha256": _mention_fingerprint(mentions),
        },
    )

    train_history = _filter_mentions(mentions, through_year=2019)
    train_query = _filter_mentions(mentions, exact_year=2020)
    train = build_project2_replay(
        train_history,
        train_query,
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        checkpoint=checkpoint,
        phase="train",
    )
    feature_indices = RANKER_FEATURE_GROUPS[args.ranker_feature_group]
    feature_names = [RANKER_FEATURE_NAMES[index] for index in feature_indices]
    nil_gate_indices = gate_feature_indices(feature_indices)
    nil_gate_feature_names = [
        GATE_FEATURE_NAMES[index] for index in nil_gate_indices
    ]
    checkpoint.mark_started("train.candidate_groups")
    train_groups = build_candidate_groups(train)
    checkpoint.mark_completed(
        "train.candidate_groups",
        {"groups": len(train_groups)},
    )
    train_known, train_new = _trial_counts(train)
    checkpoint.mark_started("train.out_of_fold_ranker")
    oof_decisions = out_of_fold_ranked_decisions(
        train_groups,
        feature_indices,
        folds=args.oof_folds,
    )
    checkpoint.mark_completed(
        "train.out_of_fold_ranker",
        {"decisions": len(oof_decisions)},
    )
    checkpoint.mark_started("train.nil_gate")
    nil_gate = fit_nil_gate(oof_decisions, nil_gate_indices)
    checkpoint.mark_completed("train.nil_gate")
    checkpoint.mark_started("train.final_ranker")
    ranker = fit_ranker(train_groups, feature_indices)
    checkpoint.mark_completed("train.final_ranker")

    validation_history = _filter_mentions(mentions, through_year=2020)
    validation_selection_query = _filter_mentions(
        mentions,
        exact_year=2021,
        paper_bucket_modulus=args.validation_modulus,
        paper_bucket=0,
        invert_bucket=True,
    )
    validation_certification_query = _filter_mentions(
        mentions,
        exact_year=2021,
        paper_bucket_modulus=args.validation_modulus,
        paper_bucket=0,
    )
    selection_replay = build_project2_replay(
        validation_history,
        validation_selection_query,
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        checkpoint=checkpoint,
        phase="validation_selection",
    )
    checkpoint.mark_started("validation_selection.rank")
    selection_groups = build_candidate_groups(selection_replay)
    selection_decisions = rank_groups(ranker, selection_groups, feature_indices)
    selection_scores = gate_scores(
        nil_gate,
        selection_decisions,
        nil_gate_indices,
    )
    checkpoint.mark_completed(
        "validation_selection.rank",
        {"groups": len(selection_groups)},
    )
    selection_known, selection_new = _trial_counts(selection_replay)
    checkpoint.mark_started("validation_selection.threshold")
    threshold_selection = select_risk_bounded_threshold(
        selection_decisions,
        selection_scores,
        known_trials=selection_known,
        new_trials=selection_new,
        confidence=args.confidence,
        max_new_false_rate=args.max_new_false_rate,
        max_wrong_known_rate=args.max_wrong_known_rate,
    )
    threshold = float(threshold_selection["threshold"])
    checkpoint.mark_completed(
        "validation_selection.threshold",
        {"selected_threshold": threshold},
    )

    certification_replay = build_project2_replay(
        validation_history,
        validation_certification_query,
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        checkpoint=checkpoint,
        phase="validation_certification",
    )
    checkpoint.mark_started("validation_certification.rank")
    certification_groups = build_candidate_groups(certification_replay)
    certification_decisions = rank_groups(
        ranker, certification_groups, feature_indices
    )
    certification_scores = gate_scores(
        nil_gate,
        certification_decisions,
        nil_gate_indices,
    )
    certification_known, certification_new = _trial_counts(
        certification_replay
    )
    certification_predictions = threshold_predictions(
        certification_replay["test_mentions"],
        certification_decisions,
        certification_scores,
        threshold,
    )
    checkpoint.mark_completed(
        "validation_certification.rank",
        {"groups": len(certification_groups)},
    )
    checkpoint.mark_started("validation_certification.risk")
    certification_risk = _risk_certificate(
        certification_replay,
        certification_predictions,
        confidence=args.confidence,
        max_new_false_rate=args.max_new_false_rate,
        max_wrong_known_rate=args.max_wrong_known_rate,
    )
    checkpoint.mark_completed("validation_certification.risk")

    evaluation_history = _filter_mentions(mentions, through_year=2021)
    evaluation_query = _filter_mentions(mentions, from_year=2022)
    evaluation = build_project2_replay(
        evaluation_history,
        evaluation_query,
        calibrated_candidate_threshold=args.calibrated_candidate_threshold,
        checkpoint=checkpoint,
        phase="comparison",
    )
    checkpoint.mark_started("comparison.rank")
    evaluation_groups = build_candidate_groups(evaluation)
    evaluation_decisions = rank_groups(ranker, evaluation_groups, feature_indices)
    evaluation_scores = gate_scores(
        nil_gate,
        evaluation_decisions,
        nil_gate_indices,
    )
    grouped_predictions = threshold_predictions(
        evaluation["test_mentions"],
        evaluation_decisions,
        evaluation_scores,
        threshold,
    )
    base = base_predictions(evaluation)
    native = native_predictions(evaluation)
    checkpoint.mark_completed(
        "comparison.rank",
        {"groups": len(evaluation_groups)},
    )
    records = evaluation["project2"]["records"]
    evaluation_known, evaluation_new = _trial_counts(evaluation)
    official_result = json.loads(args.s2and_result.read_text(encoding="utf-8"))
    if not official_result.get("complete"):
        raise ValueError("official S2AND comparator is incomplete")
    official_queries = int(
        official_result["manifest"]["selected_query_authorships"]
    )
    if official_queries != len(records):
        raise ValueError("Project Two and S2AND query cardinalities differ")

    report = {
        "schema_version": SCHEMA_VERSION,
        "contains_record_values": False,
        "development_only": True,
        "protocol": {
            "project_revision": project_revision,
            **input_hashes,
            "runtime_versions": checkpoint_protocol["runtime_versions"],
            "query_labels_used_as_features": False,
            "original_name_used": False,
            "train": {"history_through": 2019, "query_year": 2020},
            "validation": {
                "history_through": 2020,
                "query_year": 2021,
                "paper_bucket_modulus": args.validation_modulus,
            },
            "comparison": {"history_through": 2021, "query_from": 2022},
            "year_authorship_counts": {
                str(year): count for year, count in sorted(year_counts.items())
            },
        },
        "model": {
            "architecture": "grouped_lambdarank_then_binary_nil_gate",
            "ranker_feature_group": args.ranker_feature_group,
            "ranker": model_summary(ranker, feature_names),
            "nil_gate": model_summary(nil_gate, nil_gate_feature_names),
            "selected_threshold": threshold,
        },
        "training": {
            "replay": _compact_replay(train),
            "groups": len(train_groups),
            "known": train_known,
            "new": train_new,
            "oof_decisions": len(oof_decisions),
            "ranking": ranking_metrics(
                train_groups,
                oof_decisions,
                known_trials=train_known,
                new_trials=train_new,
            ),
        },
        "validation": {
            "selection_replay": _compact_replay(selection_replay),
            "certification_replay": _compact_replay(certification_replay),
            "selection_ranking": ranking_metrics(
                selection_groups,
                selection_decisions,
                known_trials=selection_known,
                new_trials=selection_new,
            ),
            "certification_ranking": ranking_metrics(
                certification_groups,
                certification_decisions,
                known_trials=certification_known,
                new_trials=certification_new,
            ),
            "threshold_selection": threshold_selection,
            "certification_risk": certification_risk,
        },
        "comparison": {
            "replay": _compact_replay(evaluation),
            "project2_grouped_ranking": ranking_metrics(
                evaluation_groups,
                evaluation_decisions,
                known_trials=evaluation_known,
                new_trials=evaluation_new,
            ),
            "project2_base": aggregate_method(evaluation, base),
            "project2_native_graph": aggregate_method(evaluation, native),
            "project2_grouped_selective": aggregate_method(
                evaluation, grouped_predictions
            ),
            "grouped_risk": _risk_certificate(
                evaluation,
                grouped_predictions,
                confidence=args.confidence,
                max_new_false_rate=args.max_new_false_rate,
                max_wrong_known_rate=args.max_wrong_known_rate,
            ),
            "paired": {
                "grouped_vs_base_known": paired_binary(
                    records, grouped_predictions, base, known=True
                ),
                "grouped_vs_base_new": paired_binary(
                    records, grouped_predictions, base, known=False
                ),
                "grouped_vs_native_known": paired_binary(
                    records, grouped_predictions, native, known=True
                ),
                "grouped_vs_native_new": paired_binary(
                    records, grouped_predictions, native, known=False
                ),
                "s2and_query_level_available": False,
                "s2and_note": (
                    "official checkpoint v1 contains aggregate contingencies only; "
                    "side-by-side metrics are valid but paired McNemar awaits v2 outcomes"
                ),
            },
            "official_s2and": {
                "manifest": official_result["manifest"],
                "linking": official_result["metrics"]["linking"],
                "clustering": official_result["metrics"]["clustering"],
            },
        },
        "complexity": {
            "wall_seconds": time.perf_counter() - wall_started,
            "cpu_seconds": time.process_time() - cpu_started,
            "peak_working_set_bytes": peak_working_set_bytes(),
            "evaluation_candidate_groups": len(evaluation_groups),
            "checkpoint": checkpoint.public_summary(),
        },
    }
    _atomic_json(args.output, report)
    checkpoint.mark_run_complete()
    comparison = report["comparison"]["project2_grouped_selective"]
    print(
        "project2_same_replay_complete "
        f"queries={len(records)} "
        f"known_recall={comparison['metrics']['known_recall']:.6f} "
        f"new_false_link={comparison['metrics']['new_author_false_link_rate']:.6f}"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--s2and-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--checkpoint-batch-size", type=int, default=5000)
    parser.add_argument("--oof-folds", type=int, default=5)
    parser.add_argument("--validation-modulus", type=int, default=5)
    parser.add_argument(
        "--ranker-feature-group",
        choices=tuple(RANKER_FEATURE_GROUPS),
        default="listwise_cross_profile",
    )
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--max-new-false-rate", type=float, default=0.005)
    parser.add_argument("--max-wrong-known-rate", type=float, default=0.01)
    parser.add_argument("--calibrated-candidate-threshold", type=float, default=0.995)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
