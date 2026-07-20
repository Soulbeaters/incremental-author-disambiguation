import json
from pathlib import Path

from experiments.compare_core_with_istina_proxy import (
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
