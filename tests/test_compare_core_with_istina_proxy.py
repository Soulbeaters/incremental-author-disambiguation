import json
from pathlib import Path

from experiments.compare_core_with_istina_proxy import (
    ablate_project2_evidence,
    apply_fallback_predictions,
    frozen_history_cluster_metrics,
    load_istina_structured_rows,
    load_real_structured_rows,
    split_positions,
)


def test_loader_removes_synthetic_original_name(tmp_path: Path):
    path = tmp_path / "rows.json"
    path.write_text(
        json.dumps([
            {
                "firstname": "Ming",
                "lastname": "Zhang",
                "orcid": "0000-0000-0000-0001",
                "original_name": "synthetic value",
            },
            {"firstname": "No", "lastname": "Label", "original_name": "x"},
        ]),
        encoding="utf-8",
    )
    rows = load_real_structured_rows(path)
    assert len(rows) == 1
    assert "original_name" not in rows[0]


def test_istina_adapter_never_reads_synthetic_original_name(tmp_path: Path):
    path = tmp_path / "istina.json"
    path.write_text(
        json.dumps([
            {
                "id": 101,
                "year": 2022,
                "authors": [
                    {
                        "author_id": 7,
                        "lastname": "Ma",
                        "firstname": "Jiaxin",
                        "middlename": "Q",
                        "original_name": "fabricated and forbidden",
                    },
                    {
                        "lastname": "Li",
                        "firstname": "Ming",
                        "original_name": "also forbidden",
                    },
                ],
            }
        ]),
        encoding="utf-8",
    )
    rows, summary = load_istina_structured_rows(path)
    assert rows == [{
        "id": "101:1",
        "firstname": "Jiaxin Q",
        "lastname": "Ma",
        "orcid": "7",
        "doi": "",
        "article_id": "101",
        "year": 2022,
        "affiliation": "",
        "coauthors": ["Li Ming"],
    }]
    assert summary["rows_missing_identity"] == 1
    assert all("original_name" not in row for row in rows)


def test_per_author_holdout_uses_only_first_repeated_mention_as_history():
    class Mention:
        def __init__(self, author_id, year, paper):
            self.label_orcid = author_id
            self.year = year
            self.paper_key = paper

    mentions = [
        Mention("a", 2021, "p2"),
        Mention("a", 2020, "p1"),
        Mention("b", 2022, "p3"),
    ]
    history, test = split_positions(
        mentions, "per-author-holdout", 2021, None, None
    )
    assert history == [1]
    assert test == [0, 2]


def test_cluster_metrics_are_aggregate_and_unresolved_are_singletons():
    records = [
        {"gold_author_id": "A"},
        {"gold_author_id": "A"},
        {"gold_author_id": "B"},
    ]
    result = frozen_history_cluster_metrics(records, ["A", None, None])
    assert result["mentions"] == 3
    assert result["gold_clusters"] == 2
    assert result["unresolved_singletons"] == 2
    assert "conflicts_detail" not in result["identity_conflicts"]
    assert set(result["b3"]) == {"precision", "recall", "f1"}


def test_frozen_fallback_only_applies_above_support_threshold():
    project2 = [
        {"decision": "new", "author_id": None},
        {"decision": "unknown", "author_id": None},
    ]
    fallback = [
        {"source_position": 10, "prediction": "A", "graph_support": 0.4, "candidate_count": 1},
        {"source_position": 11, "prediction": "B", "graph_support": 0.7, "candidate_count": 1},
    ]
    assert apply_fallback_predictions(
        fallback, project2, [10, 11], "unknown_or_new", 0.5
    ) == [None, "B"]


def test_context_ablation_returns_copies_and_removes_only_requested_fields():
    source = [{"coauthors": ["A"], "affiliation": "U", "name": "N"}]
    coauthor_ablation = ablate_project2_evidence(source, "coauthors")
    affiliation_ablation = ablate_project2_evidence(source, "affiliation")
    assert coauthor_ablation == [{"coauthors": [], "affiliation": "U", "name": "N"}]
    assert affiliation_ablation == [{"coauthors": ["A"], "affiliation": "", "name": "N"}]
    assert source == [{"coauthors": ["A"], "affiliation": "U", "name": "N"}]
