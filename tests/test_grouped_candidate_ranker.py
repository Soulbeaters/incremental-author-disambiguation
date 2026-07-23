import pytest

from experiments.grouped_candidate_ranker import (
    CandidateExample,
    CandidateGroup,
    GATE_FEATURE_NAMES,
    RANKER_FEATURE_GROUPS,
    RANKER_FEATURE_NAMES,
    build_candidate_groups,
    fit_nil_gate,
    fit_ranker,
    gate_feature_indices,
    gate_scores,
    rank_groups,
    ranking_metrics,
    select_risk_bounded_threshold,
)


def test_candidate_groups_keep_labels_out_of_features():
    replay = {
        "project2": {"records": [{
            "article_id": "paper-1",
            "decision": "unknown",
            "author_id": None,
            "candidate_count": 2,
            "gold_seen_in_history": True,
            "gold_author_id": "A",
            "name": "Test Name",
            "topk": [
                {"author_id": "B", "score": 2.0, "comparisons": {"name_sim": 0.8}},
                {"author_id": "A", "score": 1.0, "comparisons": {"name_sim": 0.9}},
            ],
        }]},
        "native": [{"prediction": "A", "graph_support": 0.7, "candidate_count": 2}],
        "profile_sizes": {"A": 3, "B": 2},
        "history_mentions_raw": [
            {
                "gold_author_id": "A",
                "year": 2020,
                "coauthors": ["Colleague"],
                "paper_embedding": [1.0, 0.0],
            },
            {
                "gold_author_id": "B",
                "year": 2019,
                "coauthors": [],
                "paper_embedding": [0.0, 1.0],
            },
        ],
        "test_mentions_raw": [{
            "year": 2022,
            "coauthors": ["Colleague"],
            "paper_embedding": [1.0, 0.0],
        }],
    }
    groups = build_candidate_groups(replay)
    assert len(groups) == 1
    assert len(groups[0].candidates) == 2
    assert sum(row.relevant for row in groups[0].candidates) == 1
    assert all(len(row.features) == len(RANKER_FEATURE_NAMES) for row in groups[0].candidates)
    assert all("A" not in {str(value) for value in row.features} for row in groups[0].candidates)
    cosine_index = RANKER_FEATURE_NAMES.index("paper_to_profile_cosine")
    available_index = RANKER_FEATURE_NAMES.index("paper_to_profile_available")
    by_author = {row.author_id: row for row in groups[0].candidates}
    assert by_author["A"].features[cosine_index] == pytest.approx(1.0)
    assert by_author["B"].features[cosine_index] == pytest.approx(0.0)
    assert by_author["A"].features[available_index] == 1.0
    assert (
        cosine_index
        not in RANKER_FEATURE_GROUPS["listwise_cross_profile"]
    )
    assert (
        cosine_index
        in RANKER_FEATURE_GROUPS["listwise_semantic_cross_profile"]
    )


def test_gate_indices_keep_old_ablation_free_of_semantic_features():
    old_ranker = RANKER_FEATURE_GROUPS["listwise_cross_profile"]
    selected = gate_feature_indices(old_ranker)
    selected_names = {GATE_FEATURE_NAMES[index] for index in selected}

    assert "paper_to_profile_cosine" not in selected_names
    assert "paper_to_profile_available" not in selected_names
    assert "ranker_top_score" in selected_names


def test_small_two_stage_model_ranks_then_rejects_nil_queries():
    pytest.importorskip("lightgbm")
    groups = []
    for index in range(80):
        known = index < 40
        positive = tuple([1.0] + [0.0] * (len(RANKER_FEATURE_NAMES) - 1))
        negative = tuple([0.0] * len(RANKER_FEATURE_NAMES))
        groups.append(CandidateGroup(
            position=index,
            paper_key=f"paper-{index}",
            known=known,
            truth=f"truth-{index}" if known else f"new-{index}",
            candidates=(
                CandidateExample(
                    author_id=f"truth-{index}" if known else f"candidate-{index}-a",
                    features=positive if known else negative,
                    relevant=known,
                ),
                CandidateExample(
                    author_id=f"candidate-{index}-b",
                    features=negative,
                    relevant=False,
                ),
            ),
        ))
    indices = tuple(range(len(RANKER_FEATURE_NAMES)))
    ranker = fit_ranker(groups, indices)
    decisions = rank_groups(ranker, groups, indices)
    metrics = ranking_metrics(groups, decisions)
    assert metrics["candidate_recall_overall"] == 1.0
    assert metrics["top1_known_accuracy_overall"] >= 0.9

    gate = fit_nil_gate(decisions)
    scores = gate_scores(gate, decisions)
    selection = select_risk_bounded_threshold(
        decisions,
        scores,
        known_trials=40,
        new_trials=40,
        confidence=0.95,
        max_new_false_rate=0.5,
        max_wrong_known_rate=0.5,
    )
    assert selection["correct_known"] >= 36
    assert selection["new_false_links"] == 0
