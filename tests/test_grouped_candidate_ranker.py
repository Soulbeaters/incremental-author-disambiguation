import copy
import math

import pytest

from experiments.grouped_candidate_ranker import (
    CandidateExample,
    CandidateGroup,
    FROZEN_MODEL_BUNDLE_SCHEMA,
    GATE_FEATURE_NAMES,
    LEGACY_FROZEN_MODEL_BUNDLE_SCHEMA,
    LEGACY_GATE_FEATURE_NAMES,
    LEGACY_RANKER_FEATURE_NAMES,
    MULTILINGUAL_RANKER_FEATURE_NAMES,
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


def test_candidate_groups_add_palladius_features_only_in_new_ablation():
    replay = {
        "project2": {"records": [{
            "article_id": "query-paper",
            "decision": "unknown",
            "author_id": None,
            "gold_seen_in_history": True,
            "gold_author_id": "A",
            "topk": [{"author_id": "A", "score": 1.0}],
        }]},
        "native": [{
            "prediction": "A",
            "graph_support": 0.0,
            "candidate_count": 1,
        }],
        "profile_sizes": {"A": 1},
        "history_mentions_raw": [{
            "article_id": "history-paper",
            "gold_author_id": "A",
            "firstname": "Jiaxing",
            "middlename": "",
            "lastname": "Ma",
            "year": 2020,
            "coauthors": [],
        }],
        "test_mentions_raw": [{
            "article_id": "query-paper",
            "firstname": "Цзясин",
            "middlename": "",
            "lastname": "Ма",
            "year": 2022,
            "coauthors": [],
        }],
    }

    group = build_candidate_groups(
        replay,
        include_multilingual=True,
    )[0]
    features = group.candidates[0].features

    assert features[
        RANKER_FEATURE_NAMES.index("family_palladius_similarity")
    ] == 1.0
    assert features[
        RANKER_FEATURE_NAMES.index("given_palladius_similarity")
    ] == 1.0
    semantic_names = {
        RANKER_FEATURE_NAMES[index]
        for index in RANKER_FEATURE_GROUPS[
            "listwise_semantic_cross_profile"
        ]
    }
    assert "given_palladius_similarity" not in semantic_names


def test_candidate_groups_add_project1_lexicon_only_in_ruzh_ablation():
    replay = {
        "project2": {"records": [{
            "article_id": "query-paper",
            "decision": "unknown",
            "gold_seen_in_history": True,
            "gold_author_id": "A",
            "topk": [{"author_id": "A", "score": 1.0}],
        }]},
        "native": [{
            "prediction": "A",
            "graph_support": 0.0,
            "candidate_count": 1,
        }],
        "profile_sizes": {"A": 1},
        "history_mentions_raw": [{
            "article_id": "history-paper",
            "gold_author_id": "A",
            "firstname": "Jiaxing",
            "middlename": "",
            "lastname": "Ma",
            "year": 2020,
            "coauthors": [],
        }],
        "test_mentions_raw": [{
            "article_id": "query-paper",
            "firstname": "Цзясин",
            "middlename": "",
            "lastname": "Ма",
            "year": 2022,
            "coauthors": [],
        }],
    }

    group = build_candidate_groups(
        replay,
        include_multilingual=True,
        include_ruzh_lexicon=True,
    )[0]
    features = group.candidates[0].features

    assert features[
        RANKER_FEATURE_NAMES.index("chinese_family_lexicon_match")
    ] == 1.0
    multilingual_names = {
        RANKER_FEATURE_NAMES[index]
        for index in RANKER_FEATURE_GROUPS[
            "listwise_multilingual_cross_profile"
        ]
    }
    assert "chinese_family_lexicon_match" not in multilingual_names


def test_multilingual_profiles_deduplicate_repeated_history_names(
    monkeypatch,
):
    observed_profile_sizes = []

    def fake_features(query, profiles):
        observed_profile_sizes.append(len(profiles))
        return (0.0,) * (
            len(MULTILINGUAL_RANKER_FEATURE_NAMES)
            - len(LEGACY_RANKER_FEATURE_NAMES)
        )

    monkeypatch.setattr(
        "experiments.grouped_candidate_ranker.best_profile_name_features",
        fake_features,
    )
    history = [{
        "article_id": f"history-{index}",
        "gold_author_id": "A",
        "firstname": "Jiaxing",
        "middlename": "",
        "lastname": "Ma",
        "year": 2020,
        "coauthors": [],
    } for index in range(100)]
    replay = {
        "project2": {"records": [{
            "article_id": "query",
            "decision": "unknown",
            "gold_seen_in_history": True,
            "gold_author_id": "A",
            "topk": [{"author_id": "A", "score": 1.0}],
        }]},
        "native": [{
            "prediction": "A",
            "graph_support": 0.0,
            "candidate_count": 1,
        }],
        "profile_sizes": {"A": len(history)},
        "history_mentions_raw": history,
        "test_mentions_raw": [{
            "article_id": "query",
            "firstname": "Цзясин",
            "middlename": "",
            "lastname": "Ма",
            "year": 2022,
            "coauthors": [],
        }],
    }

    build_candidate_groups(replay, include_multilingual=True)

    assert observed_profile_sizes == [1]


def test_gate_indices_keep_old_ablation_free_of_semantic_features():
    old_ranker = RANKER_FEATURE_GROUPS["listwise_cross_profile"]
    selected = gate_feature_indices(old_ranker)
    selected_names = {GATE_FEATURE_NAMES[index] for index in selected}

    assert "paper_to_profile_cosine" not in selected_names
    assert "paper_to_profile_available" not in selected_names
    assert "ranker_top_score" in selected_names


def test_multilingual_ablation_extends_but_does_not_change_old_group():
    semantic = RANKER_FEATURE_GROUPS["listwise_semantic_cross_profile"]
    multilingual = RANKER_FEATURE_GROUPS[
        "listwise_multilingual_cross_profile"
    ]

    assert tuple(
        RANKER_FEATURE_NAMES[index] for index in semantic
    ) == LEGACY_RANKER_FEATURE_NAMES
    assert multilingual[: len(semantic)] == semantic
    assert len(multilingual) > len(semantic)


def test_ruzh_lexicon_ablation_extends_without_changing_multilingual_group():
    multilingual = RANKER_FEATURE_GROUPS[
        "listwise_multilingual_cross_profile"
    ]
    ruzh = RANKER_FEATURE_GROUPS["listwise_ruzh_cross_profile"]

    assert tuple(
        RANKER_FEATURE_NAMES[index] for index in multilingual
    ) == MULTILINGUAL_RANKER_FEATURE_NAMES
    assert ruzh[: len(multilingual)] == multilingual
    assert len(ruzh) > len(multilingual)


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


def test_legacy_gate_summary_indices_are_remapped_by_name(monkeypatch):
    class FakeBooster:
        def __init__(self, *, model_str):
            self.model_str = model_str

        def num_feature(self):
            return 1

    class FakeLibrary:
        Booster = FakeBooster

    monkeypatch.setattr(
        "experiments.grouped_candidate_ranker._require_lightgbm",
        lambda: FakeLibrary,
    )
    import hashlib
    import json

    ranker_name = LEGACY_RANKER_FEATURE_NAMES[0]
    gate_name = "ranker_top_score"
    ranker_model = "legacy-ranker"
    gate_model = "legacy-gate"
    protocol = {"project_revision": "legacy"}
    encoded_protocol = json.dumps(
        protocol,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload = {
        "schema_version": LEGACY_FROZEN_MODEL_BUNDLE_SCHEMA,
        "contains_identity_values": False,
        "decision_threshold": 0.5,
        "protocol_sha256": hashlib.sha256(encoded_protocol).hexdigest(),
        "ranker": {
            "feature_indices": [0],
            "feature_names": [ranker_name],
            "model_sha256": hashlib.sha256(
                ranker_model.encode("utf-8")
            ).hexdigest(),
            "lightgbm_model": ranker_model,
        },
        "nil_gate": {
            "feature_indices": [
                LEGACY_GATE_FEATURE_NAMES.index(gate_name)
            ],
            "feature_names": [gate_name],
            "model_sha256": hashlib.sha256(
                gate_model.encode("utf-8")
            ).hexdigest(),
            "lightgbm_model": gate_model,
        },
        "protocol": protocol,
    }

    loaded = load_frozen_model_bundle(payload)

    assert loaded.ranker_feature_indices == (
        RANKER_FEATURE_NAMES.index(ranker_name),
    )
    assert loaded.nil_gate_feature_indices == (
        GATE_FEATURE_NAMES.index(gate_name),
    )
    assert FROZEN_MODEL_BUNDLE_SCHEMA != LEGACY_FROZEN_MODEL_BUNDLE_SCHEMA
