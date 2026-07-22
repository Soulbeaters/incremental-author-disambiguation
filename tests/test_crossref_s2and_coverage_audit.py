import io
import json

import pytest

from experiments.audit_crossref_s2and_coverage import iter_json_array


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
