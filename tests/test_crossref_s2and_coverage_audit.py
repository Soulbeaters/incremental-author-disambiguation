import io
import json

import pytest

from experiments.audit_crossref_s2and_coverage import (
    build_report,
    iter_json_array,
    iter_json_object_items,
    iter_json_records,
)


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 64])
def test_streams_top_level_array_across_chunk_boundaries(chunk_size):
    document = json.dumps([
        {"nested": [1, 2, {"quoted": "brace } and comma ,"}]},
        {"unicode": "Ма Цзясин"},
        3,
    ], ensure_ascii=False)

    assert list(iter_json_array(io.StringIO(document), chunk_size)) == [
        {"nested": [1, 2, {"quoted": "brace } and comma ,"}]},
        {"unicode": "Ма Цзясин"},
        3,
    ]


def test_rejects_non_array_and_truncated_input():
    with pytest.raises(ValueError, match="top-level JSON array"):
        list(iter_json_array(io.StringIO('{"not": "array"}'), 2))
    with pytest.raises(ValueError, match="unterminated"):
        list(iter_json_array(io.StringIO('[{"unfinished": true}'), 3))


def test_handles_one_large_item_without_reparsing_partial_prefixes():
    item = {"payload": "x" * 200_000, "nested": [{"value": 1}]}

    assert list(iter_json_array(io.StringIO(json.dumps([item])), 1024)) == [item]


def test_auto_detects_array_and_json_lines():
    expected = [{"id": 1}, {"id": 2}]
    json_lines = "\n".join(json.dumps(item) for item in expected) + "\n"

    assert list(iter_json_records(io.StringIO(json.dumps(expected)), 2)) == expected
    assert list(iter_json_records(io.StringIO(json_lines), 2)) == expected


def test_streams_top_level_object_members():
    expected = {"paper-1": [{"given": "A", "family": "B"}], "paper-2": []}

    assert dict(iter_json_object_items(io.StringIO(json.dumps(expected)), 3)) == expected


def test_author_only_report_marks_paper_context_unavailable(tmp_path):
    authors = tmp_path / "authors.json"
    authors.write_text(
        json.dumps([{
            "firstname": "Observed",
            "lastname": "Author",
            "orcid": "label-only",
            "doi": "10.example/work",
            "year": 2024,
        }]),
        encoding="utf-8",
    )

    report = build_report(authors)

    assert report["author_export"]["items"] == 1
    assert report["work_export"] == {
        "provided": False,
        "paper_context_available": False,
    }
    assert report["doi_join"] == {
        "available": False,
        "author_rows_total_with_doi": 1,
    }
    assert report["article_author_map"] == {
        "provided": False,
        "complete_paper_author_lists_available": False,
    }


def test_report_joins_complete_article_author_map_without_exposing_values(tmp_path):
    authors = tmp_path / "authors.json"
    article_map = tmp_path / "article_map.json"
    authors.write_text(
        json.dumps([{
            "firstname": "Observed",
            "lastname": "Author",
            "orcid": "label-only",
            "doi": "10.example/work",
            "article_id": "paper-1",
            "year": 2024,
        }]),
        encoding="utf-8",
    )
    article_map.write_text(
        json.dumps({
            "paper-1": [
                {"given": "Observed", "family": "Author", "orcid": "label-only"},
                {"given": "Second", "family": "Author", "orcid": ""},
            ]
        }),
        encoding="utf-8",
    )

    report = build_report(authors, article_authors_path=article_map)

    assert report["article_id_join"] == {
        "available": True,
        "distinct_joined_article_ids": 1,
        "author_rows_on_joined_article_ids": 1,
        "author_rows_total_with_article_id": 1,
    }
    assert report["article_author_map"]["author_rows"] == 2
    assert report["article_author_map"]["record_values_emitted"] is False
