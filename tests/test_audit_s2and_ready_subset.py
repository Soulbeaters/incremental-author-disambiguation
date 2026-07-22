import gzip
import json

from experiments.audit_s2and_ready_subset import build_report


def test_reports_only_aggregate_ready_subset_and_temporal_roles(tmp_path):
    authors = tmp_path / "authors.json"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    rows = [
        {"firstname": "A", "lastname": "One", "orcid": "id-1", "doi": "d1", "year": 2020},
        {"firstname": "A", "lastname": "One", "orcid": "id-1", "doi": "d2", "year": 2022},
        {"firstname": "B", "lastname": "Two", "orcid": "id-2", "doi": "d2", "year": 2022},
        {"firstname": "C", "lastname": "New", "orcid": "id-3", "doi": "d3", "year": 2023},
    ]
    authors.write_text(json.dumps(rows), encoding="utf-8")
    response_rows = [
        {
            "externalIds": {"DOI": doi},
            "title": "Observed",
            "authors": [{"name": "Raw cache only"}],
            "embedding": {"vector": [0.1] * 768},
        }
        for doi in ("d1", "d2", "d3")
    ]
    with gzip.open(cache_dir / "batch_00000_test.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"doi_digest": "digest", "rows": response_rows}, handle)

    report = build_report(authors, cache_dir)

    assert report["contains_record_values"] is False
    assert report["authorships"]["s2and_complete_specter2_subset"] == 4
    assert report["authorships"]["distinct_papers"] == 3
    assert report["authorships"]["distinct_identities"] == 3
    assert report["authorships"]["repeated_identities"] == 1
    split = report["temporal_splits"]["2020"]
    assert split["known_query_authorships"] == 1
    assert split["new_query_authorships"] == 2
    serialized = json.dumps(report)
    assert "id-1" not in serialized
    assert "Raw cache only" not in serialized
