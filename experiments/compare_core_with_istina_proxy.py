"""Compare Project Two core with the frozen ISTINA hypergraph proxy.

Only real structured fields (firstname, lastname, ORCID, DOI, year and
affiliation) are used. The known synthetic ``original_name`` field is removed
before any model object is created and is never used as a feature.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


PROJECT2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT2_ROOT))

from experiments.istina_runtime_replay import evaluate, exact_mcnemar_two_sided  # noqa: E402
from disambiguation_engine.paper_graph_rescue import predict_graph_by_paper  # noqa: E402
from disambiguation_engine.structured_name_repair import compatible_structured_author_ids  # noqa: E402
from evaluation.cluster_metrics import evaluate_all_metrics  # noqa: E402
from integrations.istina_pipeline import IstinaDisambiguationPipeline, IstinaPipelineConfig  # noqa: E402
from integrations.istina_export_quality import deduplicate_exact_author_rows  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wilson_interval_95(successes: int, total: int) -> list[float]:
    """Return a two-sided 95% Wilson score interval for a binomial rate."""

    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    rate = successes / total
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt(
        rate * (1.0 - rate) / total + z * z / (4.0 * total * total)
    ) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def load_real_structured_rows(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, list):
        raise ValueError("Expected a JSON list of Crossref author records")
    clean = []
    for source in document:
        if not isinstance(source, Mapping):
            continue
        row = {key: value for key, value in source.items() if key != "original_name"}
        if row.get("firstname") and row.get("lastname") and row.get("orcid"):
            clean.append(row)
    if any("original_name" in row for row in clean):
        raise AssertionError("synthetic original_name entered the clean dataset")
    return clean


def _structured_author_name(author: Mapping[str, Any]) -> str:
    """Build a name only from declared structured fields.

    The advisor export also contains an early synthetic ``original_name``
    column.  This adapter deliberately never reads or copies that column.
    """

    return " ".join(
        part
        for part in (
            str(author.get("lastname") or author.get("last_name") or "").strip(),
            str(author.get("firstname") or author.get("first_name") or "").strip(),
            str(author.get("middlename") or author.get("middle_name") or "").strip(),
        )
        if part
    )


def load_istina_structured_rows(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Adapt an ISTINA article export without synthetic display names.

    ``author_id`` is copied to the proxy's label-only ``orcid`` slot.  It is
    never exposed to either algorithm as an input feature.
    """

    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, list):
        raise ValueError("Expected a JSON list of ISTINA article records")
    articles, duplicates_removed = deduplicate_exact_author_rows(document)
    rows: list[dict[str, Any]] = []
    missing_identity = 0
    missing_structured_name = 0
    for article_index, article in enumerate(articles, start=1):
        authors = list(article.get("authors") or [])
        structured_names = [_structured_author_name(author) for author in authors]
        paper_id = str(
            article.get("id")
            or article.get("article_id")
            or article.get("doi")
            or article_index
        )
        for fallback_position, author in enumerate(authors, start=1):
            firstname = str(
                author.get("firstname") or author.get("first_name") or ""
            ).strip()
            middlename = str(
                author.get("middlename") or author.get("middle_name") or ""
            ).strip()
            lastname = str(
                author.get("lastname") or author.get("last_name") or ""
            ).strip()
            identity = author.get("author_id")
            if identity in (None, ""):
                identity = author.get("id")
            if identity in (None, ""):
                missing_identity += 1
                continue
            if not firstname or not lastname:
                missing_structured_name += 1
                continue
            rows.append({
                "id": f"{paper_id}:{author.get('position') or fallback_position}",
                "firstname": " ".join(part for part in (firstname, middlename) if part),
                "lastname": lastname,
                "orcid": str(identity),
                "doi": str(article.get("doi") or ""),
                "article_id": paper_id,
                "year": article.get("year"),
                "affiliation": author.get("affiliation") or "",
                "coauthors": [
                    name
                    for index, name in enumerate(structured_names)
                    if index != fallback_position - 1 and name
                ],
            })
    if any("original_name" in row for row in rows):
        raise AssertionError("synthetic original_name entered the ISTINA adapter")
    return rows, {
        "articles": len(articles),
        "exact_duplicate_author_rows_removed": duplicates_removed,
        "labeled_structured_rows": len(rows),
        "rows_missing_identity": missing_identity,
        "labeled_rows_missing_structured_name": missing_structured_name,
    }


def load_project1_proxy(project1_root: Path) -> dict[str, Any]:
    root = str(project1_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.author_disambiguation import row_to_mention
    from src.istina_hypergraph_proxy import (
        build_profiles,
        get_candidates,
        score_istina_hypergraph_proxy_paper,
    )
    return {
        "row_to_mention": row_to_mention,
        "build_profiles": build_profiles,
        "get_candidates": get_candidates,
        "score_paper": score_istina_hypergraph_proxy_paper,
    }


def build_proxy_mentions(
    rows: Iterable[Mapping[str, Any]],
    row_to_mention: Any,
) -> list[Any]:
    mentions = [row_to_mention(row, index) for index, row in enumerate(rows)]
    mentions = [
        mention
        for mention in mentions
        if mention.label_orcid
        and mention.given_tokens
        and mention.family_tokens
        and mention.year is not None
        and mention.paper_key
    ]
    if any(mention.original_name for mention in mentions):
        raise AssertionError("synthetic original_name reached proxy mentions")
    return mentions


def paper_coauthor_names(mentions: list[Any]) -> dict[int, list[str]]:
    positions_by_paper: dict[str, list[int]] = defaultdict(list)
    for position, mention in enumerate(mentions):
        positions_by_paper[mention.paper_key].append(position)
    coauthors: dict[int, list[str]] = {}
    for positions in positions_by_paper.values():
        for position in positions:
            derived = {
                mentions[other].canonical_name
                for other in positions
                if other != position
            }
            # Explicit coauthors preserve context from authors without a usable
            # identity label in the ISTINA export.  They contain normalized
            # name keys only, never labels or synthetic display names.
            derived.update(mentions[position].explicit_coauthor_keys)
            coauthors[position] = sorted(name for name in derived if name)
    return coauthors


def split_positions(
    mentions: list[Any],
    strategy: str,
    cutoff_year: int,
    test_from_year: int | None,
    test_through_year: int | None,
) -> tuple[list[int], list[int]]:
    if strategy == "temporal":
        history = [
            position for position, mention in enumerate(mentions)
            if mention.year is not None and mention.year <= cutoff_year
        ]
        test = [
            position for position, mention in enumerate(mentions)
            if mention.year is not None
            and mention.year > cutoff_year
            and (test_from_year is None or mention.year >= test_from_year)
            and (test_through_year is None or mention.year <= test_through_year)
        ]
        return history, test
    if strategy != "per-author-holdout":
        raise ValueError(f"Unsupported split strategy: {strategy}")

    grouped: dict[str, list[int]] = defaultdict(list)
    for position, mention in enumerate(mentions):
        grouped[mention.label_orcid].append(position)
    history: list[int] = []
    test: list[int] = []
    for positions in grouped.values():
        ordered = sorted(
            positions,
            key=lambda position: (
                mentions[position].year or 0,
                mentions[position].paper_key,
                position,
            ),
        )
        if len(ordered) >= 2:
            history.append(ordered[0])
            test.extend(ordered[1:])
        else:
            test.extend(ordered)
    return sorted(history), sorted(test)


def to_project2_mention(
    mention: Any,
    position: int,
    article_index: int,
    coauthors: Mapping[int, list[str]],
) -> dict[str, Any]:
    return {
        "article_index": article_index,
        "article_id": mention.paper_key,
        "position": position,
        "year": mention.year,
        "gold_author_id": mention.label_orcid,
        "name": mention.canonical_name,
        "lastname": mention.lastname,
        "firstname": mention.firstname,
        "middlename": "",
        "coauthors": list(coauthors.get(position, ())),
        "journal": "",
        "affiliation": mention.affiliation,
    }


def project2_config(
    enable_calibrated_candidate_rescue: bool = False,
    calibrated_candidate_threshold: float | None = None,
) -> IstinaPipelineConfig:
    settings: dict[str, Any] = {}
    if calibrated_candidate_threshold is not None:
        settings["calibrated_candidate_threshold"] = calibrated_candidate_threshold
    return IstinaPipelineConfig(
        mode="fs",
        accept_threshold=-0.5,
        reject_threshold=-4.0,
        min_accept_margin=1e-9,
        require_context_for_low_name_accept=True,
        enable_calibrated_candidate_rescue=enable_calibrated_candidate_rescue,
        use_remote_fallback=False,
        **settings,
    )


def evaluate_proxy(
    mentions: list[Any],
    history_positions: list[int],
    test_positions: list[int],
    api: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profiles, family_index, _ = api["build_profiles"](mentions, history_positions)
    history_ids = set(profiles)
    by_paper: dict[str, list[int]] = defaultdict(list)
    for position in test_positions:
        by_paper[mentions[position].paper_key].append(position)

    counts = Counter(
        total=0, known=0, new=0, predicted=0, correct_known=0, wrong_known=0,
        false_links_new=0, candidate_covered_known=0,
    )
    records: list[dict[str, Any]] = []
    for positions in by_paper.values():
        candidate_sets = {
            position: api["get_candidates"](
                mentions[position], profiles, family_index
            )
            for position in positions
        }
        predictions = api["score_paper"](
            positions, candidate_sets, profiles
        )
        for position in positions:
            mention = mentions[position]
            truth = mention.label_orcid
            known = truth in history_ids
            prediction, graph_support = predictions.get(position, (None, 0.0))
            covered = truth in candidate_sets[position]
            counts["total"] += 1
            counts["known" if known else "new"] += 1
            counts["predicted"] += int(prediction is not None)
            counts["candidate_covered_known"] += int(known and covered)
            correct = bool(known and prediction == truth)
            counts["correct_known"] += int(correct)
            counts["wrong_known"] += int(known and prediction is not None and not correct)
            counts["false_links_new"] += int(not known and prediction is not None)
            records.append({
                "source_position": position,
                "known": known,
                "correct": correct,
                "prediction_present": prediction is not None,
                "prediction": prediction,
                "graph_support": float(graph_support),
                "candidate_count": len(candidate_sets[position]),
                "candidate_covered": covered,
            })
    known = counts["known"]
    predicted_known = counts["correct_known"] + counts["wrong_known"]
    new = counts["new"]
    metrics = {
        "candidate_recall_known": counts["candidate_covered_known"] / known if known else 0.0,
        "top1_accuracy_known": counts["correct_known"] / known if known else 0.0,
        "precision_known_predictions": counts["correct_known"] / predicted_known if predicted_known else 0.0,
        "new_author_false_link_rate": counts["false_links_new"] / new if new else 0.0,
    }
    return {"counts": dict(counts), "metrics": metrics}, records


def compact_project2(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stats": result["stats"],
        "metrics": {
            key: value
            for key, value in result["metrics"].items()
            if not key.startswith("latency") and key != "throughput_mentions_per_second"
        },
        "candidate_retrieval": result["candidate_retrieval"],
        "stage_counts": result["stage_counts"],
    }


def project2_diagnostics(
    result: Mapping[str, Any],
    proxy_records: list[Mapping[str, Any]],
    test_positions: list[int],
) -> dict[str, Any]:
    records = list(result["records"])
    if len(records) != len(test_positions):
        raise AssertionError("Project Two output is not aligned with the test split")
    by_position = dict(zip(test_positions, records))
    known = candidate_covered = known_merge_predictions = correct = wrong_known = 0
    proxy_only_causes: Counter[str] = Counter()
    proxy_only_stages: Counter[str] = Counter()
    proxy_only_candidate_counts: Counter[str] = Counter()
    proxy_only_graph_support: Counter[str] = Counter()
    proxy_only_top1_signatures: Counter[str] = Counter()
    proxy_only_gold_ranks: Counter[str] = Counter()
    project2_only_causes: Counter[str] = Counter()

    for old in proxy_records:
        new = by_position[old["source_position"]]
        if not old["known"]:
            continue
        known += 1
        gold = str(new["gold_author_id"])
        candidate_ids = {
            str(candidate.get("author_id") or "")
            for candidate in new.get("topk") or []
        }
        covered = gold in candidate_ids
        candidate_covered += int(covered)
        is_merge = new.get("decision") == "merge"
        is_correct = bool(new.get("correct"))
        known_merge_predictions += int(is_merge)
        correct += int(is_correct)
        wrong_known += int(is_merge and not is_correct)

        if old["correct"] and not is_correct:
            if not covered:
                cause = "project2_candidate_miss"
            elif new.get("decision") == "unknown":
                cause = "project2_unknown_despite_gold_candidate"
            elif new.get("decision") == "new":
                cause = "project2_new_despite_gold_candidate"
            else:
                cause = "project2_wrong_ranking"
            proxy_only_causes[cause] += 1
            proxy_only_stages[str(new.get("stage") or "unknown")] += 1
            proxy_only_candidate_counts[str(old.get("candidate_count") or 0)] += 1
            support = float(old.get("graph_support") or 0.0)
            support_bin = (
                "zero" if support == 0.0 else
                "(0,0.5)" if support < 0.5 else
                "[0.5,1.25)" if support < 1.25 else
                "[1.25,2.0)" if support < 2.0 else
                "[2.0,+inf)"
            )
            proxy_only_graph_support[support_bin] += 1
            topk = list(new.get("topk") or [])
            gold_rank = next(
                (
                    rank
                    for rank, candidate in enumerate(topk, start=1)
                    if str(candidate.get("author_id") or "") == gold
                ),
                None,
            )
            proxy_only_gold_ranks[str(gold_rank or "missing")] += 1
            if topk:
                comparisons = topk[0].get("comparisons") or {}
                signature = "|".join(
                    str(comparisons.get(key) or "missing")
                    for key in (
                        "name_bin",
                        "coauthor_bin",
                        "affiliation_bin",
                        "orcid_bin",
                    )
                )
                proxy_only_top1_signatures[signature] += 1
        elif is_correct and not old["correct"]:
            project2_only_causes[
                "proxy_candidate_miss"
                if not old["candidate_covered"]
                else "proxy_graph_selection_error"
            ] += 1

    return {
        "known_mentions": known,
        "new_mentions": int(result["stats"]["new_gold"]),
        "candidate_covered_known": candidate_covered,
        "candidate_recall_known": candidate_covered / known if known else 0.0,
        "known_merge_predictions": known_merge_predictions,
        "correct_known": correct,
        "wrong_known": wrong_known,
        "precision_known_predictions": (
            correct / known_merge_predictions if known_merge_predictions else 0.0
        ),
        "new_author_false_link_rate": (
            result["stats"]["merge_for_new_gold"] / result["stats"]["new_gold"]
            if result["stats"]["new_gold"] else 0.0
        ),
        "false_links_new": int(result["stats"]["merge_for_new_gold"]),
        "proxy_only_error_causes": dict(sorted(proxy_only_causes.items())),
        "proxy_only_project2_stages": dict(
            sorted(proxy_only_stages.items(), key=lambda item: (-item[1], item[0]))
        ),
        "proxy_only_proxy_candidate_counts": dict(
            sorted(proxy_only_candidate_counts.items())
        ),
        "proxy_only_graph_support_bins": dict(sorted(proxy_only_graph_support.items())),
        "proxy_only_project2_gold_ranks": dict(sorted(proxy_only_gold_ranks.items())),
        "proxy_only_project2_top1_signatures": dict(
            sorted(proxy_only_top1_signatures.items())
        ),
        "project2_only_causes": dict(sorted(project2_only_causes.items())),
    }


def paired_known(
    proxy_records: list[Mapping[str, Any]],
    project2_records: list[Mapping[str, Any]],
    test_positions: list[int],
) -> dict[str, Any]:
    cells = Counter(
        both_correct=0, proxy_only_correct=0, project2_only_correct=0, both_incorrect=0
    )
    if len(project2_records) != len(test_positions):
        raise AssertionError("Project Two output is not aligned with the test split")
    project2_by_position = dict(zip(test_positions, project2_records))
    for old in proxy_records:
        new = project2_by_position[old["source_position"]]
        if not old["known"]:
            continue
        old_ok = bool(old["correct"])
        new_ok = bool(new["correct"] and new["gold_seen_in_history"])
        cell = (
            "both_correct" if old_ok and new_ok else
            "proxy_only_correct" if old_ok else
            "project2_only_correct" if new_ok else
            "both_incorrect"
        )
        cells[cell] += 1
    return {
        "n": sum(cells.values()),
        "cells": dict(cells),
        "mcnemar_exact_two_sided_p": exact_mcnemar_two_sided(
            cells["proxy_only_correct"], cells["project2_only_correct"]
        ),
    }


def evaluate_hybrid_sweep(
    fallback_records: list[Mapping[str, Any]],
    project2_records: list[Mapping[str, Any]],
    test_positions: list[int],
    paired_reference_records: list[Mapping[str, Any]] | None = None,
    paired_reference_name: str = "fallback_only",
) -> dict[str, list[dict[str, Any]]]:
    if len(project2_records) != len(test_positions):
        raise AssertionError("Project Two output is not aligned with the test split")
    project2_by_position = dict(zip(test_positions, project2_records))
    reference_by_position = {
        int(record["source_position"]): record
        for record in (paired_reference_records or fallback_records)
    }
    thresholds = (0.0, 0.5, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)
    output: dict[str, list[dict[str, Any]]] = {}
    for policy, fallback_decisions, require_unique_proxy in (
        ("unknown_only", {"unknown"}, False),
        ("unknown_or_new", {"unknown", "new"}, False),
        ("unknown_only_unique_proxy", {"unknown"}, True),
        ("unknown_or_new_unique_proxy", {"unknown", "new"}, True),
    ):
        rows = []
        for threshold in thresholds:
            counts = Counter(
                total=0, known=0, new=0, merges=0, correct_known=0,
                wrong_known=0, false_links_new=0, fallback_merges=0,
                fallback_correct_known=0, fallback_wrong_known=0,
                fallback_false_links_new=0,
                base_and_hybrid_correct=0, base_only_correct=0,
                hybrid_only_correct=0, base_and_hybrid_incorrect=0,
                reference_and_hybrid_correct=0, reference_only_correct=0,
                hybrid_only_vs_reference=0, reference_and_hybrid_incorrect=0,
            )
            for old in fallback_records:
                new = project2_by_position[old["source_position"]]
                reference = reference_by_position[old["source_position"]]
                known = bool(old["known"])
                truth = str(new["gold_author_id"])
                decision = str(new.get("decision") or "")
                prediction = (
                    str(new.get("author_id") or "")
                    if decision == "merge"
                    else ""
                )
                used_fallback = False
                if (
                    not prediction
                    and decision in fallback_decisions
                    and old.get("prediction")
                    and (
                        not require_unique_proxy
                        or int(old.get("candidate_count") or 0) == 1
                    )
                    and float(old.get("graph_support") or 0.0) >= threshold
                ):
                    prediction = str(old["prediction"])
                    used_fallback = True

                counts["total"] += 1
                counts["known" if known else "new"] += 1
                counts["merges"] += int(bool(prediction))
                correct = bool(known and prediction == truth)
                wrong_known = bool(known and prediction and prediction != truth)
                false_link_new = bool(not known and prediction)
                counts["correct_known"] += int(correct)
                counts["wrong_known"] += int(wrong_known)
                counts["false_links_new"] += int(false_link_new)
                counts["fallback_merges"] += int(used_fallback)
                counts["fallback_correct_known"] += int(used_fallback and correct)
                counts["fallback_wrong_known"] += int(used_fallback and wrong_known)
                counts["fallback_false_links_new"] += int(
                    used_fallback and false_link_new
                )
                if known:
                    base_correct = bool(new.get("correct"))
                    reference_correct = bool(reference.get("correct"))
                    counts[
                        "base_and_hybrid_correct" if base_correct and correct else
                        "base_only_correct" if base_correct else
                        "hybrid_only_correct" if correct else
                        "base_and_hybrid_incorrect"
                    ] += 1
                    counts[
                        "reference_and_hybrid_correct"
                        if reference_correct and correct else
                        "reference_only_correct" if reference_correct else
                        "hybrid_only_vs_reference" if correct else
                        "reference_and_hybrid_incorrect"
                    ] += 1

            known_predictions = counts["correct_known"] + counts["wrong_known"]
            all_links = known_predictions + counts["false_links_new"]
            rows.append({
                "threshold": threshold,
                "counts": dict(counts),
                "metrics": {
                    "known_recall": counts["correct_known"] / counts["known"],
                    "known_prediction_precision": (
                        counts["correct_known"] / known_predictions
                        if known_predictions else 0.0
                    ),
                    "all_link_precision": (
                        counts["correct_known"] / all_links if all_links else 0.0
                    ),
                    "new_author_false_link_rate": (
                        counts["false_links_new"] / counts["new"]
                        if counts["new"] else 0.0
                    ),
                },
                "paired_known": {
                    "vs_project2_base_mcnemar_exact_two_sided_p": exact_mcnemar_two_sided(
                        counts["base_only_correct"], counts["hybrid_only_correct"]
                    ),
                    "reference": paired_reference_name,
                    "vs_reference_mcnemar_exact_two_sided_p": exact_mcnemar_two_sided(
                        counts["reference_only_correct"],
                        counts["hybrid_only_vs_reference"],
                    ),
                },
            })
        output[policy] = rows
    return output


def native_graph_records(
    history_mentions: list[Mapping[str, Any]],
    project2_records: list[Mapping[str, Any]],
    test_mentions: list[Mapping[str, Any]],
    test_positions: list[int],
    repair_profiles: Any,
    time_decay_half_life_years: float | None = None,
) -> list[dict[str, Any]]:
    """Adapt native Project Two graph proposals to the paired evaluator."""

    graph_records = []
    for record, mention in zip(project2_records, test_mentions):
        enriched = dict(record)
        enriched["year"] = mention.get("year")
        enriched["graph_candidate_ids"] = compatible_structured_author_ids(
            mention, repair_profiles
        )
        graph_records.append(enriched)
    predictions = predict_graph_by_paper(
        history_mentions,
        graph_records,
        time_decay_half_life_years=time_decay_half_life_years,
    )
    output: list[dict[str, Any]] = []
    for local_position, (source_position, record) in enumerate(
        zip(test_positions, project2_records)
    ):
        proposal = predictions.get(local_position)
        truth = str(record.get("gold_author_id") or "")
        known = bool(record.get("gold_seen_in_history"))
        candidate_ids = set(graph_records[local_position]["graph_candidate_ids"])
        output.append({
            "source_position": source_position,
            "known": known,
            "correct": bool(
                known and proposal is not None and proposal.author_id == truth
            ),
            "prediction_present": proposal is not None,
            "prediction": proposal.author_id if proposal else None,
            "graph_support": proposal.support if proposal else 0.0,
            "candidate_count": len(candidate_ids),
            "candidate_covered": truth in candidate_ids,
        })
    return output


def apply_fallback_predictions(
    fallback_records: list[Mapping[str, Any]],
    project2_records: list[Mapping[str, Any]],
    test_positions: list[int],
    policy: str,
    threshold: float,
) -> list[str | None]:
    """Apply one frozen fallback rule and return aligned identity proposals."""

    fallback_decisions = (
        {"unknown"} if policy.startswith("unknown_only") else {"unknown", "new"}
    )
    require_unique = policy.endswith("unique_proxy")
    project2_by_position = dict(zip(test_positions, project2_records))
    predictions: list[str | None] = []
    for fallback in fallback_records:
        record = project2_by_position[int(fallback["source_position"])]
        prediction = (
            str(record.get("author_id") or "")
            if record.get("decision") == "merge"
            else ""
        )
        if (
            not prediction
            and str(record.get("decision") or "") in fallback_decisions
            and fallback.get("prediction")
            and (not require_unique or int(fallback.get("candidate_count") or 0) == 1)
            and float(fallback.get("graph_support") or 0.0) >= threshold
        ):
            prediction = str(fallback["prediction"])
        predictions.append(prediction or None)
    return predictions


def frozen_history_cluster_metrics(
    project2_records: list[Mapping[str, Any]],
    predictions: list[str | None],
) -> dict[str, Any]:
    """Evaluate the frozen-history online assignment as test-set clusters.

    An unresolved mention becomes a unique singleton.  Identifiers are used
    only as in-memory cluster keys and are removed from the aggregate report.
    """

    if len(project2_records) != len(predictions):
        raise AssertionError("cluster predictions are not aligned with test records")
    gold_clusters: dict[str, list[str]] = defaultdict(list)
    predicted_clusters: dict[str, list[str]] = defaultdict(list)
    for position, (record, prediction) in enumerate(
        zip(project2_records, predictions)
    ):
        mention_id = f"mention-{position}"
        gold_clusters[str(record.get("gold_author_id") or "missing")].append(
            mention_id
        )
        predicted_key = str(prediction) if prediction else f"singleton-{position}"
        predicted_clusters[predicted_key].append(mention_id)

    metrics = evaluate_all_metrics(dict(gold_clusters), dict(predicted_clusters))
    conflicts = dict(metrics["orcid_conflicts"])
    conflicts.pop("conflicts_detail", None)
    return {
        "mentions": len(project2_records),
        "gold_clusters": len(gold_clusters),
        "predicted_clusters": len(predicted_clusters),
        "unresolved_singletons": sum(prediction is None for prediction in predictions),
        "b3": metrics["b3"],
        "pairwise": metrics["pairwise"],
        "identity_conflicts": conflicts,
    }


def ablate_project2_evidence(
    mentions: list[Mapping[str, Any]],
    ablation: str,
) -> list[dict[str, Any]]:
    """Return copies with one prespecified contextual evidence family removed."""

    output = [dict(mention) for mention in mentions]
    if ablation in {"coauthors", "both"}:
        for mention in output:
            mention["coauthors"] = []
    if ablation in {"affiliation", "both"}:
        for mention in output:
            mention["affiliation"] = ""
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--dataset-format",
        choices=["crossref-orcid", "advisor-istina"],
        default="crossref-orcid",
    )
    parser.add_argument(
        "--split-strategy",
        choices=["temporal", "per-author-holdout"],
        default="temporal",
    )
    parser.add_argument("--project1-root", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, default=2021)
    parser.add_argument("--test-from-year", type=int)
    parser.add_argument("--test-through-year", type=int)
    parser.add_argument(
        "--frozen-hybrid-policy",
        choices=[
            "unknown_only",
            "unknown_or_new",
            "unknown_only_unique_proxy",
            "unknown_or_new_unique_proxy",
        ],
    )
    parser.add_argument("--frozen-hybrid-threshold", type=float)
    parser.add_argument(
        "--frozen-native-graph-policy",
        choices=[
            "unknown_only",
            "unknown_or_new",
            "unknown_only_unique_proxy",
            "unknown_or_new_unique_proxy",
        ],
    )
    parser.add_argument("--frozen-native-graph-threshold", type=float)
    parser.add_argument("--native-graph-half-life-years", type=float)
    parser.add_argument(
        "--ablate-project2-evidence",
        choices=["none", "coauthors", "affiliation", "both"],
        default="none",
    )
    parser.add_argument(
        "--enable-calibrated-candidate-rescue",
        action="store_true",
        help="Enable the already-frozen OpenAlex-trained interpretable rescue model.",
    )
    parser.add_argument("--calibrated-candidate-threshold", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.frozen_hybrid_policy is None) != (args.frozen_hybrid_threshold is None):
        parser.error(
            "--frozen-hybrid-policy and --frozen-hybrid-threshold must be supplied together"
        )
    if (args.frozen_native_graph_policy is None) != (
        args.frozen_native_graph_threshold is None
    ):
        parser.error(
            "--frozen-native-graph-policy and --frozen-native-graph-threshold "
            "must be supplied together"
        )

    adapter_summary: dict[str, Any] = {}
    if args.dataset_format == "advisor-istina":
        rows, adapter_summary = load_istina_structured_rows(args.dataset)
    else:
        rows = load_real_structured_rows(args.dataset)
    api = load_project1_proxy(args.project1_root)
    mentions = build_proxy_mentions(rows, api["row_to_mention"])
    history_positions, test_positions = split_positions(
        mentions,
        args.split_strategy,
        args.cutoff_year,
        args.test_from_year,
        args.test_through_year,
    )
    proxy, proxy_records = evaluate_proxy(
        mentions, history_positions, test_positions, api
    )

    coauthors = paper_coauthor_names(mentions)
    history = [
        to_project2_mention(mentions[position], position, position + 1, coauthors)
        for position in history_positions
    ]
    test = [
        to_project2_mention(mentions[position], position, position + 1, coauthors)
        for position in test_positions
    ]
    history = ablate_project2_evidence(history, args.ablate_project2_evidence)
    test = ablate_project2_evidence(test, args.ablate_project2_evidence)
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=project2_config(
            args.enable_calibrated_candidate_rescue,
            args.calibrated_candidate_threshold,
        ),
    )
    project2 = evaluate(pipeline, test, {})

    hybrid_sweep = evaluate_hybrid_sweep(
        proxy_records,
        project2["records"],
        test_positions,
        paired_reference_name="istina_hypergraph_proxy",
    )
    native_records = native_graph_records(
        history,
        project2["records"],
        test,
        test_positions,
            pipeline.history_state.repair_profiles,
            args.native_graph_half_life_years,
    )
    native_sweep = evaluate_hybrid_sweep(
        native_records,
        project2["records"],
        test_positions,
        paired_reference_records=proxy_records,
        paired_reference_name="istina_hypergraph_proxy",
    )
    hybrid_report: dict[str, Any]
    if args.frozen_hybrid_policy is None:
        hybrid_report = {"exploratory_hybrid_sweep": hybrid_sweep}
        selected_hybrid = None
    else:
        matching = [
            row for row in hybrid_sweep[args.frozen_hybrid_policy]
            if row["threshold"] == args.frozen_hybrid_threshold
        ]
        if len(matching) != 1:
            raise ValueError("Frozen hybrid threshold is not in the prespecified grid")
        hybrid_report = {
            "frozen_hybrid": {
                "policy": args.frozen_hybrid_policy,
                **matching[0],
            }
        }
        selected_hybrid = matching[0]

    if args.frozen_native_graph_policy is None:
        native_graph_report: dict[str, Any] = {
            "exploratory_project2_native_graph_sweep": native_sweep
        }
        selected_native_graph = None
    else:
        native_matching = [
            row for row in native_sweep[args.frozen_native_graph_policy]
            if row["threshold"] == args.frozen_native_graph_threshold
        ]
        if len(native_matching) != 1:
            raise ValueError("Frozen native graph threshold is not in the prespecified grid")
        selected_native_graph = native_matching[0]
        native_graph_report = {
            "frozen_project2_native_graph": {
                "policy": args.frozen_native_graph_policy,
                **selected_native_graph,
            }
        }

    proxy_counts = proxy["counts"]
    p2_diagnostic = project2_diagnostics(
        project2, proxy_records, test_positions
    )
    confidence_intervals = {
        "method": "two-sided 95% Wilson score interval",
        "istina_proxy": {
            "known_recall": wilson_interval_95(
                proxy_counts["correct_known"], proxy_counts["known"]
            ),
            "known_prediction_precision": wilson_interval_95(
                proxy_counts["correct_known"],
                proxy_counts["correct_known"] + proxy_counts["wrong_known"],
            ),
            "new_author_false_link_rate": wilson_interval_95(
                proxy_counts["false_links_new"], proxy_counts["new"]
            ),
        },
        "project2_core": {
            "known_recall": wilson_interval_95(
                p2_diagnostic["correct_known"], p2_diagnostic["known_mentions"]
            ),
            "known_prediction_precision": wilson_interval_95(
                p2_diagnostic["correct_known"],
                p2_diagnostic["known_merge_predictions"],
            ),
            "new_author_false_link_rate": wilson_interval_95(
                p2_diagnostic["false_links_new"], p2_diagnostic["new_mentions"]
            ),
        },
    }
    if selected_hybrid is not None:
        selected_counts = selected_hybrid["counts"]
        confidence_intervals["frozen_hybrid"] = {
            "known_recall": wilson_interval_95(
                selected_counts["correct_known"], selected_counts["known"]
            ),
            "known_prediction_precision": wilson_interval_95(
                selected_counts["correct_known"],
                selected_counts["correct_known"] + selected_counts["wrong_known"],
            ),
            "new_author_false_link_rate": wilson_interval_95(
                selected_counts["false_links_new"], selected_counts["new"]
            ),
        }
    if selected_native_graph is not None:
        native_counts = selected_native_graph["counts"]
        confidence_intervals["frozen_project2_native_graph"] = {
            "known_recall": wilson_interval_95(
                native_counts["correct_known"], native_counts["known"]
            ),
            "known_prediction_precision": wilson_interval_95(
                native_counts["correct_known"],
                native_counts["correct_known"] + native_counts["wrong_known"],
            ),
            "new_author_false_link_rate": wilson_interval_95(
                native_counts["false_links_new"], native_counts["new"]
            ),
        }

    base_predictions = [
        str(record.get("author_id") or "") or None
        if record.get("decision") == "merge"
        else None
        for record in project2["records"]
    ]
    proxy_predictions = [
        str(record.get("prediction") or "") or None
        for record in proxy_records
    ]
    cluster_report: dict[str, Any] = {
        "protocol": (
            "Frozen-history online assignment on the test partition; every "
            "unresolved mention is a separate singleton."
        ),
        "istina_hypergraph_proxy": frozen_history_cluster_metrics(
            project2["records"], proxy_predictions
        ),
        "project2_core": frozen_history_cluster_metrics(
            project2["records"], base_predictions
        ),
    }
    if args.frozen_hybrid_policy is not None:
        cluster_report["frozen_hybrid"] = frozen_history_cluster_metrics(
            project2["records"],
            apply_fallback_predictions(
                proxy_records,
                project2["records"],
                test_positions,
                args.frozen_hybrid_policy,
                args.frozen_hybrid_threshold,
            ),
        )
    if args.frozen_native_graph_policy is not None:
        cluster_report["frozen_project2_native_graph"] = frozen_history_cluster_metrics(
            project2["records"],
            apply_fallback_predictions(
                native_records,
                project2["records"],
                test_positions,
                args.frozen_native_graph_policy,
                args.frozen_native_graph_threshold,
            ),
        )

    report = {
        "protocol": {
            "dataset_sha256": sha256_file(args.dataset),
            "dataset_format": args.dataset_format,
            "split_strategy": args.split_strategy,
            "cutoff_year": args.cutoff_year,
            "test_from_year": args.test_from_year,
            "test_through_year": args.test_through_year,
            "real_structured_fields_only": True,
            "original_name_removed_and_asserted_empty": True,
            "history_mentions": len(history),
            "test_mentions": len(test),
            "project2_revision": "20966ca1cf114f4850a5eb50e1f02e716e87f214",
            "istina_proxy_source": str(args.project1_root / "src" / "istina_hypergraph_proxy.py"),
            "contains_mention_level_data": False,
            "calibrated_candidate_rescue": args.enable_calibrated_candidate_rescue,
            "calibrated_candidate_threshold": args.calibrated_candidate_threshold,
            "native_graph_half_life_years": args.native_graph_half_life_years,
            "project2_evidence_ablation": args.ablate_project2_evidence,
            "adapter_summary": adapter_summary,
        },
        "istina_hypergraph_proxy": proxy,
        "project2_core": compact_project2(project2),
        "project2_core_diagnostics": p2_diagnostic,
        "paired_known": paired_known(proxy_records, project2["records"], test_positions),
        "confidence_intervals_95": confidence_intervals,
        "clustering": cluster_report,
        **hybrid_report,
        **native_graph_report,
        "limitations": [
            "The ISTINA arm is a frozen source-faithful Python proxy, not the compiled production service.",
            "ORCID is the real identity label for this Crossref transfer benchmark.",
            "Independent ISTINA labels remain necessary for an ISTINA superiority claim.",
            (
                "Hybrid thresholds are an exploratory sweep on this validation set."
                if args.frozen_hybrid_policy is None
                else "The hybrid policy and threshold were frozen before this test run."
            ),
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
