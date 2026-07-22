from disambiguation_engine.listwise_open_set_gate import (
    FEATURE_NAMES,
    graph_proposal_features,
    select_feature_group,
)
from experiments.evaluate_listwise_graph_gate import (
    choose_threshold,
    combined_predictions,
    fixed_decision_risk_certificate,
    validation_selection_and_certification_positions,
)


class _Mention:
    def __init__(self, year, paper_key):
        self.year = year
        self.paper_key = paper_key


def test_listwise_features_use_proposal_rank_and_margin_without_gold():
    record = {
        "name": "Zhang W",
        "decision": "unknown",
        "candidate_count": 5,
        "gold_author_id": "must-not-be-read",
        "topk": [
            {
                "author_id": "A",
                "score": 3.0,
                "comparisons": {"name_sim": 0.9, "coauthor_sim": 0.5},
            },
            {"author_id": "B", "score": 2.0, "comparisons": {"name_sim": 0.8}},
        ],
    }
    features = graph_proposal_features(
        record,
        {"prediction": "B", "graph_support": 0.7, "candidate_count": 2},
        profile_size=4,
        paper_size=3,
        fixed_merge_count=1,
    )
    values = dict(zip(FEATURE_NAMES, features))
    assert values["proposal_reciprocal_rank"] == 0.5
    assert values["proposal_vs_best_other_margin"] == -1.0
    assert values["top_two_score_margin"] == 1.0
    assert len(select_feature_group(features, "graph_only")) == 6


def test_validation_threshold_respects_zero_false_link_budget():
    replay = {
        "project2": {"records": [
            {
                "decision": "unknown",
                "author_id": None,
                "gold_author_id": "A",
                "gold_seen_in_history": True,
            },
            {
                "decision": "new",
                "author_id": None,
                "gold_author_id": "NEW",
                "gold_seen_in_history": False,
            },
        ]},
        "native": [
            {"prediction": "A"},
            {"prediction": "B"},
        ],
    }
    examples = [
        {"position": 0, "known": True, "correct": True},
        {"position": 1, "known": False, "correct": False},
    ]
    selection = choose_threshold(
        replay,
        examples,
        {0: 0.9, 1: 0.8},
        max_unseen_false_rate=0.0,
        max_wrong_known=0,
    )
    assert selection["correct_rescues"] == 1
    assert selection["unseen_false_links"] == 0
    assert selection["threshold"] == 0.9


def test_layered_gate_never_removes_frozen_native_prediction():
    replay = {
        "project2": {"records": [{"decision": "unknown", "author_id": None}]},
        "native": [{"prediction": "A", "graph_support": 0.5}],
    }
    assert combined_predictions(
        replay,
        scores={},
        threshold=1.0,
        preserve_native_threshold=0.5,
    ) == ["A"]


def test_validation_certificate_split_keeps_papers_intact():
    mentions = [_Mention(2021, "history")]
    mentions.extend(
        _Mention(2022, paper)
        for paper in ["a", "a", "b", "c", "d", "e", "f", "g", "h", "i"]
    )
    history, selection, certification = validation_selection_and_certification_positions(
        mentions,
        history_through_year=2021,
        validation_year=2022,
        certification_modulus=3,
    )
    assert history == [0]
    selection_papers = {mentions[position].paper_key for position in selection}
    certification_papers = {
        mentions[position].paper_key for position in certification
    }
    assert selection_papers.isdisjoint(certification_papers)
    assert len([position for position in selection + certification if mentions[position].paper_key == "a"]) == 2


def test_risk_certificate_rejects_small_zero_error_sample():
    replay = {
        "project2": {
            "records": [
                {
                    "gold_seen_in_history": False,
                    "gold_author_id": f"new-{index}",
                }
                for index in range(100)
            ]
        }
    }
    certificate = fixed_decision_risk_certificate(
        replay,
        [None] * 100,
        confidence=0.95,
        max_unseen_false_rate=0.005,
        max_wrong_known_rate=0.01,
    )
    assert certificate["unseen_false_link"]["events"] == 0
    assert certificate["unseen_false_link"]["upper_bound"] > 0.005
    assert certificate["eligible_for_promotion"] is False
