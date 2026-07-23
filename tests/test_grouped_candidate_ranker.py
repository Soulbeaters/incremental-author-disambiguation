import copy
import math

import pytest

from experiments.grouped_candidate_ranker import (
    CandidateExample,
    CandidateGroup,
    GATE_FEATURE_NAMES,
    RANKER_FEATURE_GROUPS,
    RANKER_FEATURE_NAMES,
    RankedDecision,
    build_candidate_groups,
    fit_nil_gate,
    fit_ranker,
    freeze_model_bundle,
    gate_feature_indices,
    gate_scores,
    load_frozen_model_bundle,
    rank_groups,
    ranking_metrics,
    select_risk_bounded_threshold,
    training_score_thresholds,
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


def test_training_fixed_sequence_stops_at_first_unsafe_threshold():
    decisions = []
    scores = {}
    for position in range(100):
        known = position < 50
        truth = f"author-{position}"
        prediction = truth if known else f"candidate-{position}"
        decisions.append(RankedDecision(
            position=position,
            paper_key=f"paper-{position}",
            known=known,
            truth=truth,
            prediction=prediction,
            features=(),
        ))
        scores[position] = 0.9 if known else 0.1
    thresholds = (math.nextafter(1.0, math.inf), 0.9, 0.5, 0.1)

    selection = select_risk_bounded_threshold(
        decisions,
        scores,
        known_trials=50,
        new_trials=50,
        confidence=0.95,
        max_new_false_rate=0.3,
        max_wrong_known_rate=0.3,
        candidate_thresholds=thresholds,
        testing_method="fixed_sequence",
    )

    assert selection["threshold"] == 0.5
    assert selection["accepted"] == 50
    assert selection["new_false_links"] == 0
    assert selection["tested_points"] == 4
    assert selection["operating_points"] == 4
    assert selection["pointwise_confidence"] == 0.95
    assert selection["threshold_family_source"] == "training_scores"


def test_training_threshold_grid_is_deterministic_and_bounded():
    thresholds = training_score_thresholds(
        [0.4, 0.1, 0.3, 0.2],
        grid_size=3,
    )

    assert thresholds == tuple(sorted(set(thresholds), reverse=True))
    assert thresholds[0] > 1.0
    assert len(thresholds) <= 4


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

    gate_indices = gate_feature_indices(indices)
    bundle = freeze_model_bundle(
        ranker,
        gate,
        indices,
        gate_indices,
        selection["threshold"],
        protocol={"project_revision": "test"},
    )
    assert bundle["contains_identity_values"] is False
    assert "truth-0" not in str(bundle)

    loaded = load_frozen_model_bundle(bundle)
    loaded_decisions = rank_groups(
        loaded.ranker,
        groups,
        loaded.ranker_feature_indices,
    )
    loaded_scores = gate_scores(
        loaded.nil_gate,
        loaded_decisions,
        loaded.nil_gate_feature_indices,
    )

    assert [row.prediction for row in loaded_decisions] == [
        row.prediction for row in decisions
    ]
    assert loaded_scores == scores
    assert loaded.decision_threshold == selection["threshold"]

    tampered_protocol = copy.deepcopy(bundle)
    tampered_protocol["protocol"]["project_revision"] = "changed"
    with pytest.raises(ValueError, match="protocol hash mismatch"):
        load_frozen_model_bundle(tampered_protocol)


def test_frozen_bundle_rejects_model_tampering():
    payload = {
        "schema_version": "project2_lightgbm_bundle_v1",
        "contains_identity_values": False,
        "decision_threshold": 0.5,
        "protocol_sha256": "0" * 64,
        "ranker": {
            "feature_indices": [0],
            "feature_names": [RANKER_FEATURE_NAMES[0]],
            "model_sha256": "0" * 64,
            "lightgbm_model": "tampered",
        },
        "nil_gate": {},
        "protocol": {},
    }

    with pytest.raises(ValueError, match="model hash mismatch"):
        load_frozen_model_bundle(payload)
