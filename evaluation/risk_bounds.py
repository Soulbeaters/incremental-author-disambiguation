"""Finite-sample risk bounds for frozen disambiguation decisions.

The bound in this module is deliberately dependency-free.  It inverts the
Bernoulli Chernoff (binary-KL) lower-tail inequality, so it is conservative
for a threshold that was fixed before the observations supplied here were
seen.  Adaptive threshold selection must therefore use a different split.
"""

from __future__ import annotations

import math


def binary_kl(observed_rate: float, candidate_rate: float) -> float:
    """Return KL(Bernoulli(observed_rate) || Bernoulli(candidate_rate))."""

    if not 0.0 <= observed_rate <= 1.0:
        raise ValueError("observed_rate must be in [0, 1]")
    if not 0.0 < candidate_rate < 1.0:
        if candidate_rate == observed_rate:
            return 0.0
        return math.inf
    if observed_rate == 0.0:
        return -math.log1p(-candidate_rate)
    if observed_rate == 1.0:
        return -math.log(candidate_rate)
    return (
        observed_rate * math.log(observed_rate / candidate_rate)
        + (1.0 - observed_rate)
        * math.log((1.0 - observed_rate) / (1.0 - candidate_rate))
    )


def chernoff_kl_upper_bound(
    events: int,
    trials: int,
    *,
    confidence: float = 0.95,
) -> float:
    """Conservative one-sided upper bound for a fixed Bernoulli risk.

    Under independent Bernoulli trials, the returned value covers the true
    event probability with probability at least ``confidence``.  Returning
    1.0 for an empty sample makes an unobserved risk explicitly uncertified.
    """

    if trials < 0:
        raise ValueError("trials must be non-negative")
    if events < 0 or events > trials:
        raise ValueError("events must be between zero and trials")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if trials == 0 or events == trials:
        return 1.0

    observed = events / trials
    target = math.log(1.0 / (1.0 - confidence)) / trials
    low = observed
    high = math.nextafter(1.0, 0.0)
    for _ in range(80):
        middle = (low + high) / 2.0
        if binary_kl(observed, middle) > target:
            high = middle
        else:
            low = middle
    return high
