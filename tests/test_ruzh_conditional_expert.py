from disambiguation_engine.ruzh_conditional_expert import (
    LinkOutcomeCounts,
    joint_promotion_gate,
    route_decision,
)


def test_non_target_returns_exact_official_object():
    official = {"prediction": "official"}
    expert = {"prediction": "expert"}

    routed = route_decision(
        {"firstname": "Blexa", "lastname": "Qwerton"},
        official,
        expert,
    )

    assert routed.route == "official_s2and"
    assert routed.value is official


def test_target_uses_expert_without_reading_synthetic_names():
    expert = {"prediction": "expert"}
    promotion = joint_promotion_gate(
        LinkOutcomeCounts(10, 20, 8, 1, 1),
        LinkOutcomeCounts(10, 20, 9, 1, 1),
        non_target_trials=30,
        non_target_disagreements=0,
    )
    routed = route_decision(
        {"firstname": "Jiaxing", "lastname": "Ma"},
        {"prediction": "official"},
        expert,
        promotion=promotion,
    )

    assert routed.route == "ruzh_expert"
    assert routed.value is expert
    assert "chinese_family_and_given_shape" in routed.target_reasons


def test_unpromoted_target_falls_back_to_exact_official_object():
    official = {"prediction": "official"}
    routed = route_decision(
        {"firstname": "Jiaxing", "lastname": "Ma"},
        official,
        {"prediction": "experimental"},
    )

    assert routed.route == "official_s2and_unpromoted_target"
    assert routed.value is official


def test_joint_gate_requires_three_way_non_regression_and_real_gain():
    baseline = LinkOutcomeCounts(
        known=100,
        new=200,
        correct_known=90,
        wrong_known=5,
        false_links_new=4,
    )
    candidate = LinkOutcomeCounts(
        known=100,
        new=200,
        correct_known=92,
        wrong_known=4,
        false_links_new=4,
    )

    decision = joint_promotion_gate(
        baseline,
        candidate,
        non_target_trials=1_000,
        non_target_disagreements=0,
    )

    assert decision.passed
    assert decision.deltas["correct_known"] == 2
    assert decision.deltas["wrong_known"] == -1


def test_joint_gate_rejects_negative_optimization():
    baseline = LinkOutcomeCounts(
        known=100,
        new=200,
        correct_known=90,
        wrong_known=5,
        false_links_new=4,
    )
    candidate = LinkOutcomeCounts(
        known=100,
        new=200,
        correct_known=91,
        wrong_known=6,
        false_links_new=3,
    )

    decision = joint_promotion_gate(
        baseline,
        candidate,
        non_target_trials=1_000,
        non_target_disagreements=1,
    )

    assert not decision.passed
    assert "wrong_known_links_increased" in decision.reasons
    assert "non_target_official_fallback_changed" in decision.reasons


def test_joint_gate_rejects_parameter_churn_without_improvement():
    baseline = LinkOutcomeCounts(10, 20, 8, 1, 1)
    decision = joint_promotion_gate(
        baseline,
        baseline,
        non_target_trials=30,
        non_target_disagreements=0,
    )

    assert not decision.passed
    assert decision.reasons == ("no_strict_target_improvement",)
