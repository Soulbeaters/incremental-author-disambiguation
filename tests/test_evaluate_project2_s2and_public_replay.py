from array import array

from experiments.evaluate_project2_s2and_public_replay import (
    _filter_mentions,
    _project2_mention,
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
    row = _project2_mention(_mention("label-only", "10.test/one", 2022), 1)

    assert row["gold_author_id"] == "label-only"
    assert row["name"] == "Author A"
    assert row["coauthors"] == ["B Coauthor"]
    assert row["journal"] == "Observed journal"
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
