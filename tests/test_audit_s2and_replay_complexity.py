import gzip
import json

from experiments.audit_s2and_replay_complexity import build_report, canonical_block


def _cache(path, dois):
    rows = [
        {
            "externalIds": {"DOI": doi},
            "embedding": {"model": "specter_v2", "vector": [0.0] * 768},
        }
        for doi in dois
    ]
    payload = {"doi_digest": "fixture", "rows": rows}
    with gzip.open(path / "batch_00000_fixture.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(payload, stream)


def test_complexity_audit_separates_global_known_from_block_coverage(tmp_path):
    authors = tmp_path / "authors.json"
    cache = tmp_path / "cache"
    cache.mkdir()
    rows = [
        {"firstname": "A", "lastname": "One", "orcid": "id-1", "doi": "d1", "year": 2020},
        {"firstname": "B", "lastname": "Two", "orcid": "id-2", "doi": "d2", "year": 2020},
        {"firstname": "A", "lastname": "One", "orcid": "id-1", "doi": "d3", "year": 2022},
        {"firstname": "C", "lastname": "Three", "orcid": "id-1", "doi": "d4", "year": 2022},
        {"firstname": "A", "lastname": "One", "orcid": "id-new", "doi": "d5", "year": 2022},
    ]
    authors.write_text(json.dumps(rows), encoding="utf-8")
    _cache(cache, ["d1", "d2", "d3", "d4", "d5"])

    report = build_report(authors, cache, cutoff_year=2021)

    assert canonical_block("Ａ", "  One ") == "a one"
    assert report["authorships"] == {
        "eligible": 5,
        "history": 2,
        "query": 3,
        "known_query": 2,
        "new_query": 1,
        "known_query_covered_by_exact_block": 1,
        "known_query_missed_by_exact_block": 1,
    }
    assert report["python_exact_incremental_cost"]["total_pair_comparisons"] == 3
    assert report["contains_record_values"] is False


def test_complexity_audit_rejects_cross_split_paper(tmp_path):
    authors = tmp_path / "authors.json"
    cache = tmp_path / "cache"
    cache.mkdir()
    authors.write_text(
        json.dumps([
            {"firstname": "A", "lastname": "One", "orcid": "x", "doi": "same", "year": 2020},
            {"firstname": "B", "lastname": "Two", "orcid": "y", "doi": "same", "year": 2022},
        ]),
        encoding="utf-8",
    )
    _cache(cache, ["same"])

    try:
        build_report(authors, cache, cutoff_year=2021)
    except ValueError as exc:
        assert "temporal paper leakage" in str(exc)
    else:
        raise AssertionError("expected temporal paper leakage rejection")
