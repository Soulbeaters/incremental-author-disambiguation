from disambiguation_engine.ruzh_residual_policy import (
    ResidualPolicy,
    ResidualRow,
    apply_residual_policy,
    link_outcomes,
    select_residual_policy,
)


def _row(key, *, target, known, truth, official, expert):
    return ResidualRow(
        query_key=key,
        target=target,
        known=known,
        truth=truth,
        official=official,
        expert=expert,
        features=(0.1, 0.2),
    )


def test_residual_policy_preserves_every_non_target_decision():
    rows = [
        _row(
            "non-target",
            target=False,
            known=True,
            truth="a",
            official="a",
            expert="b",
        ),
        _row(
            "target",
            target=True,
            known=True,
            truth="a",
            official=None,
            expert="a",
        ),
    ]
    predictions = apply_residual_policy(
        rows,
        {"non-target": 1.0, "target": 1.0},
        {"non-target": 1.0, "target": 1.0},
        ResidualPolicy(0.5, 0.5),
    )

    assert predictions == ["a", "a"]


def test_selection_requires_joint_gain_without_trading_errors():
    rows = [
        _row(
            "rescue",
            target=True,
            known=True,
            truth="a",
            official=None,
            expert="a",
        ),
        _row(
            "veto-new",
            target=True,
            known=False,
            truth="new",
            official="b",
            expert="c",
        ),
        _row(
            "protected",
            target=True,
            known=True,
            truth="d",
            official="d",
            expert="e",
        ),
        _row(
            "fallback",
            target=False,
            known=True,
            truth="f",
            official="f",
            expert="g",
        ),
    ]
    replacement_scores = {
        "rescue": 0.99,
        "veto-new": 0.2,
        "protected": 0.1,
    }
    veto_scores = {
        "veto-new": 0.99,
        "protected": 0.1,
    }
    policy, deltas = select_residual_policy(
        rows,
        replacement_scores,
        veto_scores,
        replacement_thresholds=(1.0, 0.9, 0.0),
        veto_thresholds=(1.0, 0.9, 0.0),
    )
    predictions = apply_residual_policy(
        rows,
        replacement_scores,
        veto_scores,
        policy,
    )

    assert predictions == ["a", None, "d", "f"]
    assert deltas["correct_known"] == 1
    assert deltas["false_links_new"] == -1
    assert link_outcomes(rows, predictions, target=True).wrong_known == 0
