import json

import pytest

from experiments.s2and_official_adapter import (
    SPECTER2_DIMENSION,
    build_s2and_service_payload,
)


def embedding(value=0.0):
    return [value] * SPECTER2_DIMENSION


def row(paper, identity, position=0, **updates):
    value = {
        "article_id": paper,
        "firstname": "Jiaxing",
        "middlename": "",
        "lastname": "Ma",
        "author_position": position,
        "gold_author_id": identity,
        "orcid": identity,
        "title": f"Title {paper}",
        "abstract": "Observed abstract",
        "journal_name": "Journal",
        "venue": "Venue",
        "year": 2024,
        "affiliation": "MSU",
        "paper_authors": [
            {"position": 0, "author_name": "Jiaxing Ma"},
            {"position": 1, "author_name": "Andrey Example"},
        ],
    }
    value.update(updates)
    return value


def test_adapter_separates_query_labels_and_orcid_from_model_payload():
    result = build_s2and_service_payload(
        [row("history-paper", "private-history-label")],
        [row("query-paper", "private-query-label")],
        paper_embeddings={
            "history-paper": embedding(0.1),
            "query-paper": embedding(0.2),
        },
    )

    serialized = json.dumps(result.payload)
    assert "private-query-label" not in serialized
    assert "private-history-label" not in serialized
    assert "orcid" not in serialized.casefold()
    assert result.history_signature_ids == ("history:0",)
    assert result.query_signature_ids == ("query:0",)
    assert list(result.payload["cluster_seeds"]["require"].values()) == [["history:0"]]


def test_adapter_rejects_synthetic_original_name():
    history = row("history-paper", "A", original_name="Fabricated")

    with pytest.raises(ValueError, match="forbidden synthetic"):
        build_s2and_service_payload(
            [history],
            [row("query-paper", "B")],
            paper_embeddings={
                "history-paper": embedding(),
                "query-paper": embedding(),
            },
        )


def test_adapter_rejects_paper_leakage_between_history_and_query():
    with pytest.raises(ValueError, match="paper leakage"):
        build_s2and_service_payload(
            [row("same-paper", "A")],
            [row("same-paper", "B", position=1)],
            paper_embeddings={"same-paper": embedding()},
        )


def test_adapter_requires_complete_paper_context_and_specter2():
    incomplete = row("history-paper", "A")
    del incomplete["paper_authors"]

    with pytest.raises(ValueError, match="paper_authors"):
        build_s2and_service_payload(
            [incomplete],
            [row("query-paper", "B")],
            paper_embeddings={
                "history-paper": embedding(),
                "query-paper": embedding(),
            },
        )

    with pytest.raises(ValueError, match="missing SPECTER2"):
        build_s2and_service_payload(
            [row("history-paper", "A")],
            [row("query-paper", "B")],
            paper_embeddings={"history-paper": embedding()},
        )

    with pytest.raises(ValueError, match="absent from"):
        build_s2and_service_payload(
            [row("history-paper", "A", author_position=3)],
            [row("query-paper", "B")],
            paper_embeddings={
                "history-paper": embedding(),
                "query-paper": embedding(),
            },
        )


def test_adapter_is_deterministic_and_reports_only_aggregate_coverage():
    kwargs = {
        "history_rows": [row("history-paper", "A")],
        "query_rows": [row("query-paper", "B")],
        "paper_embeddings": {
            "history-paper": embedding(0.1),
            "query-paper": embedding(0.2),
        },
    }

    first = build_s2and_service_payload(**kwargs)
    second = build_s2and_service_payload(**kwargs)

    assert first == second
    assert first.coverage == {
        "history_signatures": 1,
        "query_signatures": 1,
        "papers": 2,
        "papers_with_title": 2,
        "papers_with_abstract": 2,
        "signatures_with_affiliation": 2,
        "papers_with_specter2": 2,
    }
