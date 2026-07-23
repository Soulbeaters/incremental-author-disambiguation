"""Conservative ISTINA-oriented repair for local NEW/UNKNOWN decisions.

The main Fellegi-Sunter layer remains unchanged.  This module is a narrow
second pass for records with structured family/given fields or ISTINA-style
``Family I. O.`` display names.  A repair is accepted only for one known local
profile and uses same-paper exclusion plus explicit coauthor thresholds for
abbreviated names.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple


TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def normalized_tokens(value: str) -> Tuple[str, ...]:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return tuple(token for token in TOKEN_RE.findall(text) if token)


def normalized_name_key(value: str) -> str:
    return " ".join(normalized_tokens(value))


def _field(record: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(record.get(name) or "").strip()
        if value:
            return value
    return ""


def structured_name_parts(record: Mapping[str, Any]) -> Tuple[str, Tuple[str, ...]]:
    """Return ``(family_key, given_tokens)`` without changing source data.

    ISTINA exports normally provide split fields.  A small minority contain
    only citation-style names; for those, the first token is the family name.
    """

    family = _field(record, "lastname", "last_name", "surname")
    first = _field(record, "firstname", "first_name")
    middle = _field(record, "middlename", "middle_name")
    # ``original_name`` is an early fabricated export field and is never
    # eligible for parsing or diagnostics.  ``name`` is retained only for
    # source-observed citation strings in older adapters.
    display_name = _field(record, "name")

    if not family and display_name:
        display_tokens = TOKEN_RE.findall(
            unicodedata.normalize("NFKC", display_name)
        )
        if display_tokens:
            family = display_tokens[0]
            if not first and len(display_tokens) > 1:
                first = display_tokens[1]
            if not middle and len(display_tokens) > 2:
                middle = " ".join(display_tokens[2:])

    family_key = "".join(normalized_tokens(family))
    given_tokens = normalized_tokens(" ".join(part for part in (first, middle) if part))
    return family_key, given_tokens


def given_relation(left: Tuple[str, ...], right: Tuple[str, ...]) -> str:
    if left == right:
        return "exact"
    if not left or not right:
        return "missing"
    if left[0] == right[0] and (
        left == right[: len(left)] or right == left[: len(right)]
    ):
        return "prefix"

    left_initials = tuple(token[:1] for token in left if token)
    right_initials = tuple(token[:1] for token in right if token)
    if not left_initials or not right_initials:
        return "different"
    shortest = min(len(left_initials), len(right_initials))
    if (
        left_initials[:shortest] == right_initials[:shortest]
        and any(len(token) == 1 for token in left + right)
    ):
        return "initial_compatible"
    return "different"


def coauthor_keys(values: Iterable[str]) -> frozenset[str]:
    keys = {normalized_name_key(value) for value in values if str(value or "").strip()}
    keys.discard("")
    return frozenset(keys)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, start=1):
        current = [index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class ProfileMention:
    author_id: str
    family_key: str
    given_tokens: Tuple[str, ...]
    coauthors: frozenset[str]
    affiliation_key: str
    article_id: str
    name: str


@dataclass(frozen=True)
class RepairProfileIndex:
    by_family: Dict[str, Tuple[ProfileMention, ...]]
    quarantined_author_ids: Tuple[str, ...]


@dataclass(frozen=True)
class StructuredRepairDecision:
    accepted: bool
    reason: str
    author_id: Optional[str] = None
    relation: Optional[str] = None
    coauthor_jaccard: float = 0.0
    history_name: Optional[str] = None


def compatible_structured_author_ids(
    mention: Mapping[str, Any],
    profiles: RepairProfileIndex,
) -> Tuple[str, ...]:
    """Return known identities compatible with a structured signature.

    Initial-compatible profiles are included as ambiguity blockers even though
    they are never sufficient by themselves for an automatic merge.
    """

    family_key, given_tokens = structured_name_parts(mention)
    current_article_id = str(mention.get("article_id") or "")
    author_ids = {
        profile.author_id
        for profile in profiles.by_family.get(family_key, ())
        if not (current_article_id and profile.article_id == current_article_id)
        and given_relation(profile.given_tokens, given_tokens)
        in {"exact", "prefix", "initial_compatible"}
    }
    return tuple(sorted(author_ids))


def decide_strict_name_repair(
    mention: Mapping[str, Any],
    profiles: RepairProfileIndex,
) -> StructuredRepairDecision:
    """Accept only one full-token exact/prefix structured-name identity.

    Initial-only names are deliberately excluded because a unique local
    candidate does not make common signatures such as ``S Li`` identities.
    """

    family_key, given_tokens = structured_name_parts(mention)

    def is_informative(family: str, given: Sequence[str]) -> bool:
        given_length = sum(len(token) for token in given)
        has_full_given_token = any(len(token) > 1 for token in given)
        if has_full_given_token:
            return len(family) + given_length >= 8
        return len(family) >= 5 and given_length >= 2

    if not is_informative(family_key, given_tokens):
        return StructuredRepairDecision(False, "missing_informative_structured_name")
    current_article_id = str(mention.get("article_id") or "")
    accepted_by_author: Dict[str, StructuredRepairDecision] = {}
    for profile in profiles.by_family.get(family_key, ()):
        if current_article_id and profile.article_id == current_article_id:
            continue
        if not is_informative(profile.family_key, profile.given_tokens):
            continue
        relation = given_relation(profile.given_tokens, given_tokens)
        if relation not in {"exact", "prefix"}:
            continue
        accepted_by_author[profile.author_id] = StructuredRepairDecision(
            True,
            f"unique_informative_structured_name_{relation}",
            author_id=profile.author_id,
            relation=relation,
            history_name=profile.name,
        )
    if not accepted_by_author:
        return StructuredRepairDecision(False, "no_informative_structured_name_match")
    if len(accepted_by_author) != 1:
        return StructuredRepairDecision(False, "ambiguous_informative_structured_names")
    accepted = next(iter(accepted_by_author.values()))
    compatible_ids = compatible_structured_author_ids(mention, profiles)
    if any(author_id != accepted.author_id for author_id in compatible_ids):
        return StructuredRepairDecision(
            False,
            "initial_compatible_identity_blocks_strict_name_repair",
        )
    return accepted


def decide_unique_non_cjk_initial_repair(
    mention: Mapping[str, Any],
    profiles: RepairProfileIndex,
    is_known_cjk_surname: Optional[Callable[[str], bool]],
) -> StructuredRepairDecision:
    """Repair a unique non-CJK initial signature, failing closed on risk data.

    A surname occurring for one local identity is not globally unique.  The
    rule is therefore disabled unless the multilingual name module can first
    exclude known CJK surnames, where homonym risk is especially high.
    """

    if not callable(is_known_cjk_surname):
        return StructuredRepairDecision(False, "surname_risk_checker_unavailable")
    family_key, given_tokens = structured_name_parts(mention)
    if len(family_key) < 4 or not given_tokens:
        return StructuredRepairDecision(False, "uninformative_initial_signature")
    if is_known_cjk_surname(family_key):
        return StructuredRepairDecision(False, "known_cjk_surname_requires_context")

    current_article_id = str(mention.get("article_id") or "")
    profiles_by_author: Dict[str, List[ProfileMention]] = {}
    for profile in profiles.by_family.get(family_key, ()):
        if current_article_id and profile.article_id == current_article_id:
            continue
        profiles_by_author.setdefault(profile.author_id, []).append(profile)
    if len(profiles_by_author) != 1:
        return StructuredRepairDecision(False, "non_unique_family_identity")

    author_id, author_profiles = next(iter(profiles_by_author.items()))
    relations = {
        given_relation(profile.given_tokens, given_tokens)
        for profile in author_profiles
    }
    if "exact" in relations or "prefix" in relations:
        return StructuredRepairDecision(False, "full_signature_handled_elsewhere")
    if "initial_compatible" not in relations:
        return StructuredRepairDecision(False, "initial_signature_not_compatible")
    history_name = min((profile.name for profile in author_profiles), default=None)
    return StructuredRepairDecision(
        True,
        "unique_non_cjk_initial_signature",
        author_id=author_id,
        relation="initial_compatible",
        history_name=history_name,
    )


def _author_id(record: Mapping[str, Any]) -> str:
    value = record.get("gold_author_id")
    if value in (None, ""):
        value = record.get("author_id")
    return "" if value in (None, "") else str(value)


def build_repair_profiles(history_mentions: Iterable[Mapping[str, Any]]) -> RepairProfileIndex:
    grouped: Dict[str, List[ProfileMention]] = {}
    for mention in history_mentions:
        author_id = _author_id(mention)
        family_key, given_tokens = structured_name_parts(mention)
        if not author_id or not family_key or not given_tokens:
            continue
        grouped.setdefault(author_id, []).append(ProfileMention(
            author_id=author_id,
            family_key=family_key,
            given_tokens=given_tokens,
            coauthors=coauthor_keys(mention.get("coauthors") or []),
            affiliation_key=normalized_name_key(mention.get("affiliation") or ""),
            article_id=str(mention.get("article_id") or ""),
            name=str(mention.get("name") or ""),
        ))

    quarantined = set()
    for author_id, mentions in grouped.items():
        families = sorted({mention.family_key for mention in mentions})
        if any(
            _levenshtein(left, right) > 1
            for index, left in enumerate(families)
            for right in families[index + 1:]
        ):
            quarantined.add(author_id)

    by_family: Dict[str, List[ProfileMention]] = {}
    for author_id, mentions in grouped.items():
        if author_id in quarantined:
            continue
        for mention in mentions:
            by_family.setdefault(mention.family_key, []).append(mention)

    return RepairProfileIndex(
        by_family={
            family: tuple(sorted(items, key=lambda item: (item.author_id, item.article_id, item.name)))
            for family, items in by_family.items()
        },
        quarantined_author_ids=tuple(sorted(quarantined)),
    )


def _accepted_relation(
    history_given: Tuple[str, ...],
    current_given: Tuple[str, ...],
    coauthor_similarity: float,
    affiliation_exact: bool,
) -> Optional[str]:
    relation = given_relation(history_given, current_given)
    # Exact names are not identities: common full names such as ``Wei Chen``
    # occur for multiple real researchers.  Require independent graph context
    # for both full and initial-only exact matches.
    if relation == "exact" and coauthor_similarity >= 0.12:
        return relation
    if relation == "prefix" and coauthor_similarity >= 0.16:
        return relation
    if relation == "initial_compatible" and (
        coauthor_similarity >= 0.12
        or affiliation_exact
    ):
        return relation
    return None


def decide_structured_repair(
    mention: Mapping[str, Any],
    profiles: RepairProfileIndex,
) -> StructuredRepairDecision:
    family_key, given_tokens = structured_name_parts(mention)
    if not family_key or not given_tokens:
        return StructuredRepairDecision(False, "missing_structured_name")

    current_article_id = str(mention.get("article_id") or "")
    current_coauthors = coauthor_keys(mention.get("coauthors") or [])
    current_affiliation = normalized_name_key(mention.get("affiliation") or "")
    accepted_by_author: Dict[str, StructuredRepairDecision] = {}
    same_paper_author_ids = {
        profile.author_id
        for profile in profiles.by_family.get(family_key, ())
        if current_article_id and profile.article_id == current_article_id
    }

    for profile in profiles.by_family.get(family_key, ()):
        if profile.author_id in same_paper_author_ids:
            continue
        coauthor_similarity = jaccard(profile.coauthors, current_coauthors)
        affiliation_exact = bool(
            current_affiliation
            and profile.affiliation_key
            and current_affiliation == profile.affiliation_key
        )
        relation = _accepted_relation(
            profile.given_tokens,
            given_tokens,
            coauthor_similarity,
            affiliation_exact,
        )
        if relation is None:
            continue
        evidence = []
        if coauthor_similarity >= 0.12:
            evidence.append("coauthor")
        if affiliation_exact:
            evidence.append("affiliation")
        candidate = StructuredRepairDecision(
            True,
            f"unique_known_profile_{relation}_{'+'.join(evidence)}",
            author_id=profile.author_id,
            relation=relation,
            coauthor_jaccard=coauthor_similarity,
            history_name=profile.name,
        )
        previous = accepted_by_author.get(profile.author_id)
        if previous is None or candidate.coauthor_jaccard > previous.coauthor_jaccard:
            accepted_by_author[profile.author_id] = candidate

    if not accepted_by_author:
        reason = "same_paper_candidate_rejected" if same_paper_author_ids else "insufficient_repair_evidence"
        return StructuredRepairDecision(False, reason)
    if len(accepted_by_author) != 1:
        return StructuredRepairDecision(False, "ambiguous_known_profiles")
    return next(iter(accepted_by_author.values()))
