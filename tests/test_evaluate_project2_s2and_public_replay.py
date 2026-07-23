from array import array
from argparse import Namespace

import pytest

from experiments.evaluate_project2_s2and_public_replay import (
    ReplayCheckpoint,
    _filter_mentions,
    _project2_mention,
    _ruzh_subgroup,
    _validate_temporal_protocol,
)
from experiments.s2and_public_replay import (
    ObservedPaperAuthor,
    PaperContext,
    ReplayMention,
)


def _mention(identity, doi, year, position=0):
    authors = (
        ObservedPaperAuthor("a", "author", "A Author"),
        ObservedPaperAuthor("b", "coauthor", "B Coauthor"),
    )
    paper = PaperContext(
        doi,
        "Observed title",
        "Observed abstract",
        "Observed journal",
        "Observed venue",
        array("f", [0.0] * 768),
    )
    return ReplayMention(
        doi,
        identity,
        "A",
        "Author",
        "Institute",
        year,
        position,
        authors,
        paper,
    )


def test_project2_adapter_uses_real_structured_context_only():
    mention = _mention("label-only", "10.test/one", 2022)
    row = _project2_mention(mention, 1)

    assert row["gold_author_id"] == "label-only"
    assert row["name"] == "Author A"
    assert row["coauthors"] == ["B Coauthor"]
    assert row["journal"] == "Observed journal"
    assert row["paper_embedding"] is mention.paper.embedding
    assert "original_name" not in row
    assert "orcid" not in row


def test_temporal_and_paper_bucket_filters_keep_roles_disjoint():
    mentions = [
        _mention("a", "10.test/history", 2019),
        _mention("b", "10.test/train", 2020),
        _mention("c", "10.test/validation", 2021),
        _mention("d", "10.test/test", 2022),
    ]

    history = _filter_mentions(mentions, through_year=2019)
    train = _filter_mentions(mentions, exact_year=2020)
    evaluation = _filter_mentions(mentions, from_year=2022)

    assert [row.year for row in history] == [2019]
    assert [row.year for row in train] == [2020]
    assert [row.year for row in evaluation] == [2022]
    assert not ({row.doi for row in history} & {row.doi for row in evaluation})


def test_late_temporal_protocol_is_valid():
    args = Namespace(
        train_history_through=2022,
        train_query_year=2023,
        validation_history_through=2023,
        validation_query_year=2024,
        comparison_history_through=2024,
        comparison_query_from=2025,
    )

    _validate_temporal_protocol(args)


def test_temporal_protocol_rejects_comparison_overlap():
    args = Namespace(
        train_history_through=2022,
        train_query_year=2023,
        validation_history_through=2023,
        validation_query_year=2024,
        comparison_history_through=2025,
        comparison_query_from=2025,
    )

    with pytest.raises(ValueError, match="temporal protocol"):
        _validate_temporal_protocol(args)


def test_ruzh_subgroup_reports_only_target_queries():
    replay = {
        "project2": {
            "records": [
                {
                    "gold_seen_in_history": True,
                    "gold_author_id": "target-author",
                },
                {
                    "gold_seen_in_history": False,
                    "gold_author_id": "other-author",
                },
            ],
        },
        "test_mentions_raw": [
            {
                "firstname": "Jiaxing",
                "middlename": "",
                "lastname": "Ma",
            },
            {
                "firstname": "Alice",
                "middlename": "",
                "lastname": "Smith",
            },
        ],
    }

    result = _ruzh_subgroup(replay, ["target-author", "wrong"])

    assert result["target_queries"] == 1
    assert result["metrics"]["known_recall"] == 1.0
    assert result["counts"]["new"] == 0


def test_replay_checkpoint_resumes_validated_batches_without_raw_progress(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_evaluate(_pipeline, mentions, _service_records):
        calls.append(len(mentions))
        records = [
            {
                **mention,
                "decision": "new",
                "author_id": None,
                "stage": "test",
                "correct": True,
                "gold_seen_in_history": False,
                "latency_ms": 1.0,
            }
            for mention in mentions
        ]
        return {
            "stats": {
                "total": len(records),
                "new_gold": len(records),
                "new": len(records),
                "correct_new": len(records),
            },
            "stage_counts": {"test": len(records)},
            "candidate_retrieval": {
                "truncated_mentions": 0,
                "candidate_pool_total": 0,
                "scored_candidate_total": 0,
            },
            "legacy_shadow": {"paired_table": {}},
            "elapsed_seconds": float(len(records)),
            "error_samples": [],
            "records": records,
        }

    monkeypatch.setattr(
        "experiments.evaluate_project2_s2and_public_replay.evaluate",
        fake_evaluate,
    )
    mentions = [
        {
            "article_id": f"10.test/{index}",
            "gold_author_id": f"id-{index}",
            "position": 0,
            "year": 2022,
        }
        for index in range(5)
    ]
    manifest = {"project_revision": "test", "data_sha256": "abc"}
    first = ReplayCheckpoint(
        tmp_path,
        signature="signature",
        manifest=manifest,
        batch_size=2,
    )

    result = first.evaluate_batches("comparison.evaluate", object(), mentions)

    assert calls == [2, 2, 1]
    assert len(result["records"]) == 5
    assert first.progress["contains_record_values"] is False
    assert "gold_author_id" not in first.progress_path.read_text(encoding="utf-8")

    calls.clear()
    resumed = ReplayCheckpoint(
        tmp_path,
        signature="signature",
        manifest=manifest,
        batch_size=2,
    )
    resumed_result = resumed.evaluate_batches(
        "comparison.evaluate",
        object(),
        mentions,
    )

    assert calls == []
    assert resumed_result["records"] == result["records"]
    assert (
        resumed.progress["phases"]["comparison.evaluate"]["reused_batches"]
        == 3
    )
