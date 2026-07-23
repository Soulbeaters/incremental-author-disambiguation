"""Train an unchanged stock-S2AND control on the public temporal development data.

This runner uses the official S2AND ``ANDData``, ``FeaturizationInfo``,
``PairwiseModeler`` and ``Clusterer`` APIs.  It does not add Project Two
features.  The result therefore measures ordinary in-domain retraining and
hyperparameter adaptation, not a method contribution.

S2AND and Hyperopt output is redirected to a run-local log so stdout remains
bounded.  The raw feature payload and source identities are never written.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import pickle
import platform
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import sha256_file  # noqa: E402
from experiments.s2and_public_replay import load_replay_corpus  # noqa: E402
from experiments.s2and_stock_training_adapter import (  # noqa: E402
    build_stock_s2and_training_data,
    exact_time_split_ratios,
    select_mentions_by_block_fraction,
    verify_official_time_split,
)


RESULT_SCHEMA_VERSION = "project2_stock_s2and_public_training_v1"


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


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_pickle(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _observed_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _binary_metrics(features: Any, labels: Any, classifier: Any) -> dict[str, Any]:
    import numpy as np
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    y = np.asarray(labels, dtype=int)
    if len(y) == 0 or len(np.unique(y)) != 2:
        raise ValueError("stock-S2AND evaluation pairs must contain both classes")
    probability = classifier.predict_proba(features)[:, 1]
    return {
        "pairs": int(len(y)),
        "positive_pairs": int(y.sum()),
        "negative_pairs": int(len(y) - y.sum()),
        "roc_auc": float(roc_auc_score(y, probability)),
        "average_precision": float(average_precision_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
    }


def _input_manifest(
    args: argparse.Namespace,
    *,
    project_revision: str,
    s2and_revision: str,
) -> dict[str, Any]:
    enrichment_manifest = args.enrichment_dir / "aggregate_manifest.json"
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "development_only": True,
        "control_interpretation": (
            "unchanged stock S2AND retrained on in-domain public development labels; "
            "parameter adaptation, not Project Two novelty"
        ),
        "project_revision": project_revision,
        "s2and_revision": s2and_revision,
        "authors_sha256": sha256_file(args.authors),
        "article_authors_sha256": sha256_file(args.article_authors),
        "enrichment_manifest_sha256": sha256_file(enrichment_manifest),
        "years": {
            "train_through": int(args.train_through_year),
            "validation": int(args.validation_year),
            "test": int(args.test_year),
        },
        "pair_samples": {
            "train": int(args.train_pairs),
            "validation": int(args.validation_pairs),
            "test": int(args.test_pairs),
        },
        "optimization_iterations": {
            "pairwise": int(args.pairwise_iterations),
            "cluster_eps": int(args.cluster_iterations),
        },
        "random_seed": int(args.random_seed),
        "n_jobs": int(args.n_jobs),
        "block_fraction": float(args.block_fraction),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.n_jobs <= 0:
        raise ValueError("n-jobs must be positive")
    if min(
        args.train_pairs,
        args.validation_pairs,
        args.test_pairs,
        args.pairwise_iterations,
        args.cluster_iterations,
    ) <= 0:
        raise ValueError("pair counts and optimization iterations must be positive")
    if not (
        args.train_through_year < args.validation_year < args.test_year
    ):
        raise ValueError("expected train-through-year < validation-year < test-year")

    project_dirty = _git_output(
        ["status", "--porcelain", "--untracked-files=all"],
        PROJECT_ROOT,
    )
    if project_dirty:
        raise RuntimeError("formal stock-S2AND training requires a clean project worktree")
    s2and_dirty = _git_output(
        ["status", "--porcelain", "--untracked-files=all"],
        args.s2and_repo,
    )
    if s2and_dirty:
        raise RuntimeError("formal stock-S2AND training requires a clean S2AND checkout")

    args.run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["S2AND_BACKEND"] = "python"
    os.environ["S2AND_CACHE"] = str(args.s2and_cache.resolve())
    os.environ["MPLCONFIGDIR"] = str((args.run_dir / "mpl-cache").resolve())
    os.environ["TQDM_DISABLE"] = "1"
    sys.path.insert(0, str(args.s2and_repo.resolve()))

    project_revision = _git_output(["rev-parse", "HEAD"], PROJECT_ROOT)
    s2and_revision = _git_output(["rev-parse", "HEAD"], args.s2and_repo)
    manifest = _input_manifest(
        args,
        project_revision=project_revision,
        s2and_revision=s2and_revision,
    )
    run_signature = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest["run_signature"] = run_signature

    started = time.perf_counter()
    stages: dict[str, float] = {}
    peak_rss = _observed_rss_bytes()
    print(
        "stock_s2and_training_start "
        f"revision={project_revision[:12]} run={run_signature[:12]}",
        flush=True,
    )

    stage_started = time.perf_counter()
    corpus = load_replay_corpus(
        args.authors,
        args.article_authors,
        args.enrichment_dir,
        cutoff_year=args.test_year,
    )
    mentions = [
        mention
        for history, query in corpus.blocks.values()
        for mention in (*history, *query)
        if mention.year <= args.test_year
    ]
    mentions, block_sample_audit = select_mentions_by_block_fraction(
        mentions,
        args.block_fraction,
    )
    training_data = build_stock_s2and_training_data(
        mentions,
        train_through_year=args.train_through_year,
        validation_year=args.validation_year,
        test_year=args.test_year,
    )
    del corpus, mentions
    gc.collect()
    stages["load_and_adapt_seconds"] = time.perf_counter() - stage_started
    peak_rss = max(peak_rss, _observed_rss_bytes())
    for role, requested in (
        ("train", args.train_pairs),
        ("validation", args.validation_pairs),
        ("test", args.test_pairs),
    ):
        available = training_data.audit["pair_opportunities"][role][
            "within_block_possible_pairs"
        ]
        if available < requested:
            raise ValueError(
                f"registered {role} block sample has {available} pairs; "
                f"{requested} requested"
            )
    print(
        "stock_s2and_training_data "
        f"train={len(training_data.train_signature_ids)} "
        f"validation={len(training_data.validation_signature_ids)} "
        f"test={len(training_data.test_signature_ids)}",
        flush=True,
    )

    train_ratio, validation_ratio, test_ratio = exact_time_split_ratios(
        len(training_data.train_signature_ids),
        len(training_data.validation_signature_ids),
        len(training_data.test_signature_ids),
    )
    log_path = args.run_dir / "training.log"
    with log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
        with redirect_stdout(log_handle), redirect_stderr(log_handle):
            from hyperopt import hp
            from s2and.data import ANDData
            from s2and.featurizer import FeaturizationInfo, featurize
            from s2and.model import Clusterer, FastCluster, PairwiseModeler

            stage_started = time.perf_counter()
            dataset = ANDData(
                signatures=training_data.payload["signatures"],
                papers=training_data.payload["papers"],
                clusters=training_data.clusters,
                specter_embeddings=training_data.payload["paper_embeddings"],
                name=f"project2-stock-{run_signature[:12]}",
                mode="train",
                block_type="s2",
                unit_of_data_split="time",
                train_ratio=train_ratio,
                val_ratio=validation_ratio,
                test_ratio=test_ratio,
                train_pairs_size=args.train_pairs,
                val_pairs_size=args.validation_pairs,
                test_pairs_size=args.test_pairs,
                pair_sampling_mode="within_block_random",
                random_seed=args.random_seed,
                load_name_counts=True,
                n_jobs=args.n_jobs,
                preprocess=True,
                use_orcid_id=False,
                use_sinonym_overwrite=False,
                compute_reference_features=True,
            )
            split_counts = verify_official_time_split(dataset, training_data)
            training_audit = training_data.audit
            del training_data
            gc.collect()
            stages["anddata_seconds"] = time.perf_counter() - stage_started

            stage_started = time.perf_counter()
            featurization_info = FeaturizationInfo()
            train, validation, test = featurize(
                dataset,
                featurization_info,
                n_jobs=args.n_jobs,
                use_cache=True,
            )
            stages["featurize_seconds"] = time.perf_counter() - stage_started

            X_train, y_train, _train_nameless = train
            X_validation, y_validation, _validation_nameless = validation
            X_test, y_test, _test_nameless = test
            stage_started = time.perf_counter()
            pairwise_model = PairwiseModeler(
                n_iter=args.pairwise_iterations,
                monotone_constraints=(
                    featurization_info.lightgbm_monotone_constraints
                ),
                n_jobs=args.n_jobs,
                random_state=args.random_seed,
            )
            pairwise_model.fit(
                X_train,
                y_train,
                X_validation,
                y_validation,
            )
            stages["pairwise_fit_seconds"] = time.perf_counter() - stage_started
            pairwise_metrics = {
                "validation": _binary_metrics(
                    X_validation, y_validation, pairwise_model.classifier
                ),
                "test": _binary_metrics(X_test, y_test, pairwise_model.classifier),
            }

            stage_started = time.perf_counter()
            clusterer = Clusterer(
                featurization_info,
                pairwise_model,
                cluster_model=FastCluster(linkage="average"),
                search_space={"eps": hp.uniform("eps", 0, 1)},
                n_iter=args.cluster_iterations,
                n_jobs=args.n_jobs,
                random_state=args.random_seed,
            )
            clusterer.fit(dataset)
            stages["cluster_fit_seconds"] = time.perf_counter() - stage_started

    peak_rss = max(peak_rss, _observed_rss_bytes())
    model_path = args.run_dir / "clusterer.pkl"
    _atomic_pickle(model_path, clusterer)
    model_sha256 = sha256_file(model_path)
    stages["total_seconds"] = time.perf_counter() - started

    versions = {
        package: importlib.metadata.version(package)
        for package in (
            "s2and",
            "numpy",
            "scikit-learn",
            "lightgbm",
            "hyperopt",
        )
    }
    result = {
        **manifest,
        "contains_record_values": False,
        "complete": True,
        "audit": training_audit,
        "block_sample": block_sample_audit,
        "official_split_counts": split_counts,
        "pairwise_metrics": pairwise_metrics,
        "model": {
            "filename": model_path.name,
            "sha256": model_sha256,
            "pairwise_best_params": _json_safe(pairwise_model.best_params),
            "cluster_best_params": _json_safe(clusterer.best_params),
            "feature_names": list(featurization_info.get_feature_names()),
        },
        "runtime": {
            "stages": stages,
            "observed_peak_rss_bytes": peak_rss,
            "python": platform.python_version(),
            "packages": versions,
        },
        "claim_boundary": {
            "is_official_frozen_model": False,
            "is_stock_s2and_retraining_control": True,
            "is_project2_method_contribution": False,
            "is_final_blind_test": False,
        },
    }
    _atomic_json(args.run_dir / "training_result.json", result)
    print(
        "stock_s2and_training_complete "
        f"model_sha256={model_sha256[:12]} "
        f"validation_auc={pairwise_metrics['validation']['roc_auc']:.6f} "
        f"test_auc={pairwise_metrics['test']['roc_auc']:.6f} "
        f"seconds={stages['total_seconds']:.1f}",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--article-authors", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--s2and-repo", type=Path, required=True)
    parser.add_argument("--s2and-cache", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--train-through-year", type=int, default=2022)
    parser.add_argument("--validation-year", type=int, default=2023)
    parser.add_argument("--test-year", type=int, default=2024)
    parser.add_argument("--train-pairs", type=int, default=100_000)
    parser.add_argument("--validation-pairs", type=int, default=10_000)
    parser.add_argument("--test-pairs", type=int, default=10_000)
    parser.add_argument("--pairwise-iterations", type=int, default=25)
    parser.add_argument("--cluster-iterations", type=int, default=25)
    parser.add_argument("--random-seed", type=int, default=1111)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--block-fraction", type=float, default=0.30)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
