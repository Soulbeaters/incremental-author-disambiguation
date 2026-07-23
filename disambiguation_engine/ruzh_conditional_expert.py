"""Fail-safe routing and joint promotion gate for the RuZh expert."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .ruzh_name_evidence import RuZhNameEvidence


@dataclass(frozen=True, slots=True)
class RoutedDecision:
    value: Any
    route: str
    target_reasons: tuple[str, ...]


def route_decision(
    query: Mapping[str, Any],
    official_s2and: Any,
    ruzh_expert: Any,
    *,
    promotion: PromotionGateDecision | None = None,
) -> RoutedDecision:
    """Use the expert only for the prespecified target stratum.

    The exact official object is returned outside the target stratum.  This
    makes non-target equality testable and prevents accidental global changes.
    """

    evidence = RuZhNameEvidence.from_mapping(query)
    if not evidence.target:
        return RoutedDecision(
            value=official_s2and,
            route="official_s2and",
            target_reasons=(),
        )
    if promotion is None or not promotion.passed:
        return RoutedDecision(
            value=official_s2and,
            route="official_s2and_unpromoted_target",
            target_reasons=evidence.reasons,
        )
    return RoutedDecision(
        value=ruzh_expert,
        route="ruzh_expert",
        target_reasons=evidence.reasons,
    )


@dataclass(frozen=True, slots=True)
class LinkOutcomeCounts:
    known: int
    new: int
    correct_known: int
    wrong_known: int
    false_links_new: int

    def __post_init__(self) -> None:
        values = (
            self.known,
            self.new,
            self.correct_known,
            self.wrong_known,
            self.false_links_new,
        )
        if any(value < 0 for value in values):
            raise ValueError("link outcome counts must be non-negative")
        if self.correct_known + self.wrong_known > self.known:
            raise ValueError("known outcomes exceed known trials")
        if self.false_links_new > self.new:
            raise ValueError("new-author false links exceed new trials")

    @property
    def known_recall(self) -> float:
        return self.correct_known / self.known if self.known else 0.0

    @property
    def wrong_known_rate(self) -> float:
        return self.wrong_known / self.known if self.known else 0.0

    @property
    def new_false_link_rate(self) -> float:
        return self.false_links_new / self.new if self.new else 0.0


@dataclass(frozen=True, slots=True)
class PromotionGateDecision:
    passed: bool
    reasons: tuple[str, ...]
    deltas: Mapping[str, int]


def joint_promotion_gate(
    baseline: LinkOutcomeCounts,
    candidate: LinkOutcomeCounts,
    *,
    non_target_trials: int,
    non_target_disagreements: int,
) -> PromotionGateDecision:
    """Require zero regression on all three link outcomes.

    Denominators must be identical.  Passing additionally requires at least
    one strict target improvement; parameter changes that merely move errors
    between the three outcomes are rejected.
    """

    if baseline.known != candidate.known or baseline.new != candidate.new:
        raise ValueError("baseline and candidate must use identical target trials")
    if non_target_trials < 0 or not 0 <= non_target_disagreements <= non_target_trials:
        raise ValueError("invalid non-target equality counts")

    deltas = {
        "correct_known": candidate.correct_known - baseline.correct_known,
        "wrong_known": candidate.wrong_known - baseline.wrong_known,
        "false_links_new": (
            candidate.false_links_new - baseline.false_links_new
        ),
        "non_target_disagreements": non_target_disagreements,
    }
    reasons: list[str] = []
    if baseline.known <= 0:
        reasons.append("no_target_known_trials")
    if baseline.new <= 0:
        reasons.append("no_target_new_trials")
    if deltas["correct_known"] < 0:
        reasons.append("known_correct_links_regressed")
    if deltas["wrong_known"] > 0:
        reasons.append("wrong_known_links_increased")
    if deltas["false_links_new"] > 0:
        reasons.append("new_author_false_links_increased")
    if non_target_disagreements:
        reasons.append("non_target_official_fallback_changed")
    strict_improvement = (
        deltas["correct_known"] > 0
        or deltas["wrong_known"] < 0
        or deltas["false_links_new"] < 0
    )
    if not strict_improvement:
        reasons.append("no_strict_target_improvement")
    return PromotionGateDecision(
        passed=not reasons,
        reasons=tuple(reasons),
        deltas=deltas,
    )


__all__ = [
    "LinkOutcomeCounts",
    "PromotionGateDecision",
    "RoutedDecision",
    "joint_promotion_gate",
    "route_decision",
]
