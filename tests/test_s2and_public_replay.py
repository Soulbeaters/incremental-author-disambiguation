import gzip
import json

from experiments.s2and_public_replay import (
    adapter_inputs,
    deterministic_query_blocks,
    load_replay_corpus,
    resolve_author_position,
    ObservedPaperAuthor,
)


def _write_cache(path):
    rows = []
    for doi in ("10.test/history", "10.test/query", "10.test/ambiguous"):
        rows.append({
            "externalIds": {"DOI": doi},
            "title": "Observed paper",
            "abstract": "Observed abstract",
            "venue": "Observed venue",
            "journal": {"name": "Observed journal"},
            "embedding": {"model": "specter_v2", "vector": [0.1] * 768},
        })
    with gzip.open(path / "batch_00000_fixture.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"doi_digest": "fixture", "rows": rows}, stream)


def test_position_resolution_rejects_ambiguous_initials():
    authors = (
        ObservedPaperAuthor("john", "smith", "John Smith"),
        ObservedPaperAuthor("jane", "smith", "Jane Smith"),
    )

    assert resolve_author_position("John", "Smith", authors) == (0, "exact")
    assert resolve_author_position("J", "Smith", authors) == (None, "ambiguous_prefix")


def test_loader_whitelists_features_and_physically_hides_query_label(tmp_path):
    authors_path = tmp_path / "authors.json"
    map_path = tmp_path / "article_map.json"
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    _write_cache(cache_path)
    authors_path.write_text(
        json.dumps([
            {
                "firstname": "Alice",
                "lastname": "Author",
                "orcid": "identity-1",
                "doi": "10.test/history",
                "article_id": "paper-history",
                "year": 2020,
                "affiliation": "Institute",
                "original_name": "forbidden synthetic value",
            },
            {
                "firstname": "A",
                "lastname": "Author",
                "orcid": "identity-1",
                "doi": "10.test/query",
                "article_id": "paper-query",
                "year": 2022,
                "affiliation": "Institute",
                "original_name": "forbidden synthetic value",
            },
        ]),
        encoding="utf-8",
    )
    map_path.write_text(
        json.dumps({
            "paper-history": [{"given": "Alice", "family": "Author", "orcid": "identity-1"}],
            "paper-query": [{"given": "Alice", "family": "Author", "orcid": "identity-1"}],
        }),
        encoding="utf-8",
    )

    corpus = load_replay_corpus(
        authors_path,
        map_path,
        cache_path,
        cutoff_year=2021,
    )
    blocks = deterministic_query_blocks(corpus)
    history, query, query_labels, embeddings = adapter_inputs(corpus, blocks)

    assert corpus.history_count == 1
    assert corpus.query_count == 1
    assert history[0]["gold_author_id"] == "identity-1"
    assert "gold_author_id" not in query[0]
    assert "orcid" not in query[0]
    assert "original_name" not in query[0]
    assert query_labels[0].identity == "identity-1"
    assert set(embeddings) == {"10.test/history", "10.test/query"}
