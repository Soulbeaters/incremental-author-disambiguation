import pytest

from experiments.run_s2and_official_public_baseline import (
    Checkpoint,
    aggregate_block_payloads,
    evaluate_block,
)
from experiments.s2and_public_replay import (
    ObservedPaperAuthor,
    PaperContext,
    ReplayMention,
)
from array import array


def _mention(identity, year):
    author = ObservedPaperAuthor("a", "author", "A Author")
    paper = PaperContext("doi", "title", "", "journal", "venue", array("f", [0.0] * 768))
    return ReplayMention("doi", identity, "A", "Author", "", year, 0, (author,), paper)


def test_block_evaluation_counts_open_set_links_and_contingencies():
    history = [_mention("known-1", 2020), _mention("known-2", 2020)]
    queries = [
        _mention("known-1", 2022),
        _mention("known-2", 2022),
        _mention("new-1", 2022),
        _mention("new-2", 2022),
    ]
    identities = {"known-1": 0, "known-2": 1, "new-1": 2, "new-2": 3}
    payload = evaluate_block(
        block_ordinal=7,
        history_signature_ids=["h0", "h1"],
        query_signature_ids=["q0", "q1", "q2", "q3"],
        history_mentions=history,
        query_mentions=queries,
        identity_index=identities,
        global_history_identity_indices={0, 1},
        clusters={
            "c0": ["h0", "q0"],
            "c1": ["h1", "q1", "q2"],
            "c2": ["q3"],
        },
        phase_b_mode="exact",
        elapsed_seconds=0.25,
    )

    assert payload["counts"] == {
        "total": 4,
        "known": 2,
        "candidate_covered_known": 2,
        "predicted_links": 3,
        "correct_known": 2,
        "wrong_known": 0,
        "known_nil": 0,
        "new": 2,
        "false_links_new": 1,
        "seed_conflict_queries": 0,
    }
    aggregate = aggregate_block_payloads([payload])
    assert aggregate["linking"]["known_recall"] == 1.0
    assert aggregate["linking"]["new_author_false_link_rate"] == 0.5
    assert aggregate["linking"]["accepted_link_precision"] == pytest.approx(2 / 3)
    assert aggregate["clustering"]["b3"]["f1"] < 1.0


def test_checkpoint_is_resumable_and_rejects_changed_manifest(tmp_path):
    path = tmp_path / "checkpoint.sqlite3"
    manifest = {"run_signature": "frozen", "selected_blocks": 1}
    checkpoint = Checkpoint(path, manifest)
    checkpoint.put(
        0,
        {
            "counts": {"total": 1, "new": 1},
            "contingency": [[0, "new:0:0", 1]],
            "history": 0,
            "query": 1,
            "theoretical_pairs": 0,
            "phase_b_mode": "exact",
            "elapsed_seconds": 0.01,
        },
    )
    checkpoint.close()

    resumed = Checkpoint(path, manifest)
    assert resumed.completed() == {0}
    assert len(resumed.payloads()) == 1
    resumed.close()
    with pytest.raises(ValueError, match="manifest"):
        Checkpoint(path, {"run_signature": "changed", "selected_blocks": 1})
