import pytest

from experiments.semantic_scholar_specter_enrichment import (
    _read_cache,
    _write_cache,
    aggregate_rows,
    batches,
    fetch_batch,
    normalize_doi,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.1000/ABC", "10.1000/abc"),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),
        ("doi:10.1000/ABC", "10.1000/abc"),
    ],
)
def test_normalizes_public_doi_identifiers(value, expected):
    assert normalize_doi(value) == expected


def test_batches_are_bounded_and_deterministic():
    assert list(batches(["a", "b", "c"], 2)) == [(0, ["a", "b"]), (1, ["c"])]
    with pytest.raises(ValueError, match="1..500"):
        list(batches(["a"], 501))


def test_aggregate_rows_counts_only_complete_specter2_vectors():
    rows = [
        {
            "title": "Observed",
            "abstract": "Observed",
            "venue": "Venue",
            "authors": [{"name": "Private in raw cache only"}],
            "embedding": {"model": "specter_v2", "vector": [0.0] * 768},
        },
        None,
        {"title": "Second", "embedding": {"vector": [0.0]}},
    ]

    assert aggregate_rows(rows) == {
        "matched": 2,
        "with_title": 2,
        "with_abstract": 1,
        "with_venue": 1,
        "with_authors": 1,
        "with_specter2": 1,
    }


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_fetch_batch_uses_doi_ids_and_never_requires_api_key():
    session = FakeSession([FakeResponse(200, [{"paperId": "public"}])])

    rows = fetch_batch(session, ["10.1000/example"], api_key=None)

    assert rows == [{"paperId": "public"}]
    _, kwargs = session.calls[0]
    assert kwargs["json"] == {"ids": ["DOI:10.1000/example"]}
    assert "x-api-key" not in kwargs["headers"]


def test_fetch_batch_reports_only_status_on_non_retryable_failure():
    session = FakeSession([FakeResponse(400, {"sensitive": "must not leak"})])

    with pytest.raises(RuntimeError, match="HTTP 400") as error:
        fetch_batch(session, ["10.1000/example"], api_key=None)

    assert "sensitive" not in str(error.value)


def test_cache_is_gzip_compressed_and_round_trips(tmp_path):
    path = tmp_path / "batch.json.gz"
    payload = {"rows": [{"embedding": {"vector": [0.1] * 768}}]}

    _write_cache(path, payload)

    assert path.read_bytes()[:2] == b"\x1f\x8b"
    assert _read_cache(path) == payload
