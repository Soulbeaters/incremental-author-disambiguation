from array import array

import pytest

from experiments.s2and_public_replay import (
    ObservedPaperAuthor,
    PaperContext,
    ReplayMention,
)
from experiments.s2and_stock_training_adapter import (
    build_stock_s2and_training_data,
    exact_time_split_ratios,
    select_mentions_by_block_fraction,
    verify_official_time_split,
)
from experiments.run_s2and_stock_public_training import _observed_rss_bytes


def _mention(
    doi: str,
    identity: str,
    year: int,
    *,
    first: str = "A",
    last: str = "Smith",
    position: int = 0,
) -> ReplayMention:
    author = ObservedPaperAuthor(first.casefold(), last.casefold(), f"{first} {last}")
    return ReplayMention(
        doi=doi,
        identity=identity,
        first=first,
        last=last,
        affiliation="Verified University",
        year=year,
        author_position=position,
        paper_authors=(author,),
        paper=PaperContext(
            doi=doi,
            title=f"Real title {doi}",
            abstract="Observed abstract",
            journal_name="Observed Journal",
            venue="Observed Journal",
            embedding=array("f", [0.0] * 768),
        ),
    )


def test_builds_hashed_supervision_and_exact_temporal_roles():
    mentions = [
        _mention("10.1/a", "0000-id-a", 2022),
        _mention("10.1/b", "0000-id-a", 2022),
        _mention("10.1/c", "0000-id-a", 2023),
        _mention("10.1/d", "0000-id-b", 2023),
        _mention("10.1/e", "0000-id-a", 2024),
        _mention("10.1/f", "0000-id-c", 2024),
        _mention("10.1/g", "future-id", 2025),
    ]

    result = build_stock_s2and_training_data(mentions)

    assert result.audit["signatures"] == {
        "train": 2,
        "validation": 2,
        "test": 2,
    }
    assert len(result.payload["signatures"]) == 6
    assert len(result.clusters) == 3
    assert all(key.startswith("cluster:") for key in result.clusters)
    boundary = repr(result.payload).casefold()
    assert "0000-id" not in boundary
    assert "original_name" not in boundary
    assert "orcid" not in boundary
    assert "future-id" not in repr(result)


def test_exact_ratios_match_official_integer_boundaries():
    ratios = exact_time_split_ratios(10, 3, 4)
    assert sum(ratios) == 1.0
    assert int(17 * ratios[0]) == 10
    assert int(17 * ratios[1]) == 3


def test_training_runner_observes_nonzero_process_memory():
    assert _observed_rss_bytes() > 0


def test_rejects_same_paper_on_two_temporal_sides():
    mentions = [
        _mention("10.1/a", "id-a", 2022),
        _mention("10.1/a", "id-b", 2023),
        _mention("10.1/c", "id-c", 2024),
    ]
    with pytest.raises(ValueError, match="paper leakage"):
        build_stock_s2and_training_data(mentions)


def test_block_sampling_is_label_independent_and_keeps_complete_blocks():
    mentions = [
        _mention("10.1/a", "identity-a", 2022, first="A", last="One"),
        _mention("10.1/b", "identity-b", 2023, first="A", last="One"),
        _mention("10.1/c", "identity-c", 2024, first="B", last="Two"),
        _mention("10.1/d", "identity-d", 2022, first="C", last="Three"),
    ]
    selected, audit = select_mentions_by_block_fraction(mentions, 0.5)
    selected_blocks = {mention.block for mention in selected}
    assert audit["selected_blocks"] == 2
    assert all(
        (mention in selected) == (mention.block in selected_blocks)
        for mention in mentions
    )

    relabelled = [
        _mention(
            mention.doi,
            f"changed-{index}",
            mention.year,
            first=mention.first,
            last=mention.last,
        )
        for index, mention in enumerate(mentions)
    ]
    selected_relabelled, _ = select_mentions_by_block_fraction(relabelled, 0.5)
    assert {mention.block for mention in selected_relabelled} == selected_blocks


class _SplitDataset:
    def split_cluster_signatures(self):
        return (
            {"a": ["history:0"]},
            {"a": ["history:1"]},
            {"a": ["history:2"]},
        )


def test_verifies_official_split_against_registered_ids():
    result = build_stock_s2and_training_data(
        [
            _mention("10.1/a", "id-a", 2022),
            _mention("10.1/b", "id-a", 2023),
            _mention("10.1/c", "id-a", 2024),
        ]
    )
    assert verify_official_time_split(_SplitDataset(), result) == {
        "train": 1,
        "validation": 1,
        "test": 1,
    }
