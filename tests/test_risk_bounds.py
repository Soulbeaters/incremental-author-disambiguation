import math

import pytest

from evaluation.risk_bounds import binary_kl, chernoff_kl_upper_bound


def test_zero_event_bound_matches_closed_form():
    expected = 1.0 - math.pow(0.05, 1.0 / 100)
    assert chernoff_kl_upper_bound(0, 100, confidence=0.95) == pytest.approx(
        expected
    )


def test_bound_contains_empirical_rate_and_tightens_with_more_trials():
    small = chernoff_kl_upper_bound(1, 100, confidence=0.95)
    large = chernoff_kl_upper_bound(10, 1000, confidence=0.95)
    assert 0.01 < large < small < 1.0


def test_empty_sample_is_not_certified():
    assert chernoff_kl_upper_bound(0, 0) == 1.0


@pytest.mark.parametrize(
    ("events", "trials"),
    [(-1, 10), (11, 10), (0, -1)],
)
def test_invalid_counts_are_rejected(events, trials):
    with pytest.raises(ValueError):
        chernoff_kl_upper_bound(events, trials)


def test_binary_kl_is_zero_on_the_diagonal():
    assert binary_kl(0.25, 0.25) == pytest.approx(0.0)
