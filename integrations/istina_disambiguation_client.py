#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe adapter for the existing ISTINA disambiguation service.

The service is useful as a candidate generator, but its ``result_id`` is not
safe enough to be used as a final decision in known short-family-name cases.
This adapter keeps the fix query-only and exposes a conservative validation
step for the local risk-control layer.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

import requests

from models.author import AuthorRecord


DEFAULT_ISTINA_DISAMBIGUATION_URL = "http://93.180.23.185:9091/"


def _clean_name_token(value: str) -> str:
    value = (value or "").lower().strip()
    return "".join(ch for ch in value if ch.isalnum())


def _has_cyrillic(value: str) -> bool:
    return any("\u0400" <= ch <= "\u04ff" for ch in value or "")


def _exported_author_name(author: Dict[str, Any]) -> str:
    original_name = (author.get("original_name") or author.get("name") or "").strip()
    if original_name:
        return original_name

    parts = [
        (author.get("lastname") or author.get("last_name") or "").strip(),
        (author.get("firstname") or author.get("first_name") or "").strip(),
        (author.get("middlename") or author.get("middle_name") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _article_identifier(article: Dict[str, Any]) -> str:
    return str(
        article.get("id")
        or article.get("article_id")
        or article.get("doi")
        or "unknown"
    )


@dataclass(frozen=True)
class IstinaServiceAuthor:
    """Name payload accepted by the ISTINA service."""

    last_name: str
    first_name: str
    middle_name: str = ""

    def as_payload(self) -> Dict[str, str]:
        return {
            "last_name": self.last_name,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
        }


@dataclass(frozen=True)
class IstinaServiceCandidate:
    """One candidate returned by the ISTINA service."""

    id: str
    last_name: str
    first_name: str
    middle_name: str
    name_similarity: float
    raw: Dict[str, Any]


@dataclass(frozen=True)
class IstinaServiceDecision:
    """Conservative local interpretation of a service response."""

    accepted: bool
    reason: str
    candidate: Optional[IstinaServiceCandidate] = None


class IstinaDisambiguationClient:
    """Small adapter around the advisor-provided ISTINA service."""

    def __init__(
        self,
        service_url: str = DEFAULT_ISTINA_DISAMBIGUATION_URL,
        timeout: float = 30.0,
        post_func: Optional[Callable[..., Any]] = None,
        trust_env: bool = False,
    ) -> None:
        self.service_url = service_url
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        if post_func is not None:
            self._post = post_func
        else:
            # The advisor service is reached directly by IP. Inheriting a
            # workstation HTTP_PROXY can turn a healthy direct response into
            # a proxy-generated 503, so proxy use must be an explicit opt-in.
            self._session = requests.Session()
            self._session.trust_env = trust_env
            self._post = self._session.post

    @staticmethod
    def from_exported_author(
        author: Dict[str, Any],
        repair_short_family: bool = True,
    ) -> IstinaServiceAuthor:
        """Build a service author from an ISTINA-like export row.

        The short-family-name repair is query-only. It does not modify exported
        data and should not be stored back into ISTINA.
        """

        last_name = (author.get("lastname") or author.get("last_name") or "").strip()
        first_name = (author.get("firstname") or author.get("first_name") or "").strip()
        middle_name = (author.get("middlename") or author.get("middle_name") or "").strip()

        if repair_short_family and not first_name and not middle_name and " " in last_name:
            parts = [part for part in last_name.split() if part]
            if len(parts) == 2:
                last_name, first_name = parts

        if repair_short_family and needs_short_family_middle_guard(last_name, first_name, middle_name):
            middle_name = "ч" if _has_cyrillic(last_name + first_name) else "x"

        return IstinaServiceAuthor(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
        )

    def request_candidates(
        self,
        authors: Iterable[IstinaServiceAuthor],
        man_id: int,
    ) -> Dict[str, Any]:
        payload = {
            "authors": [author.as_payload() for author in authors],
            "man_id": man_id,
        }
        response = self._post(
            self.service_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return json.loads(response.content.decode("utf-8", errors="replace"))

    @staticmethod
    def parse_candidate_groups(response: Dict[str, Any]) -> List[List[IstinaServiceCandidate]]:
        groups: List[List[IstinaServiceCandidate]] = []
        for group in response.get("authors") or []:
            parsed_group: List[IstinaServiceCandidate] = []
            for raw_candidate in group or []:
                parsed_group.append(
                    IstinaServiceCandidate(
                        id=str(raw_candidate.get("id", "")),
                        last_name=str(raw_candidate.get("last_name", "") or ""),
                        first_name=str(raw_candidate.get("first_name", "") or ""),
                        middle_name=str(raw_candidate.get("middle_name", "") or ""),
                        name_similarity=float(raw_candidate.get("name_similarity") or 0.0),
                        raw=dict(raw_candidate),
                    )
                )
            groups.append(parsed_group)
        return groups

    @staticmethod
    def conservative_local_decision(
        query_author: IstinaServiceAuthor,
        response: Dict[str, Any],
        min_name_similarity: float = 0.84,
    ) -> IstinaServiceDecision:
        """Interpret service output without blindly trusting ``result_id``.

        Accept only when all conditions hold:
        - first name is not just an initial;
        - exactly one candidate has exact normalized last + first name;
        - that candidate has high service name similarity;
        - service ``result_id`` agrees with that candidate.
        """

        query_last = _clean_name_token(query_author.last_name)
        query_first = _clean_name_token(query_author.first_name)

        if not query_last or not query_first:
            return IstinaServiceDecision(False, "missing_query_name")

        if len(query_first) <= 1:
            return IstinaServiceDecision(False, "ambiguous_initial_firstname")

        service_result_ids = [str(value) for value in response.get("result_id") or []]
        service_result_id = service_result_ids[0] if service_result_ids else "0"
        candidate_groups = IstinaDisambiguationClient.parse_candidate_groups(response)
        first_group = candidate_groups[0] if candidate_groups else []

        exact_candidates = [
            candidate
            for candidate in first_group
            if _clean_name_token(candidate.last_name) == query_last
            and _clean_name_token(candidate.first_name) == query_first
            and candidate.name_similarity >= min_name_similarity
        ]

        if len(exact_candidates) != 1:
            return IstinaServiceDecision(False, "not_unique_exact_candidate")

        candidate = exact_candidates[0]
        if candidate.id != service_result_id:
            return IstinaServiceDecision(False, "service_result_disagrees")

        return IstinaServiceDecision(True, "service_agrees_with_unique_exact_candidate", candidate)

    @staticmethod
    def known_author_unknown_fallback(
        response: Dict[str, Any],
        known_author_ids: Iterable[str],
        min_name_similarity: float = 0.85,
    ) -> IstinaServiceDecision:
        """Validate a service fallback after the local layer returns UNKNOWN.

        The service result is accepted only when it refers to an author already
        present in the caller's local history, the same ID is present in the
        returned candidate group, and its service name similarity is high.
        This prevents the remote service from turning a locally unseen author
        into an unsafe merge.
        """

        known_ids = {str(author_id) for author_id in known_author_ids}
        service_result_ids = [str(value) for value in response.get("result_id") or []]
        service_result_id = service_result_ids[0] if service_result_ids else "0"
        if service_result_id in {"0", "", "None"}:
            return IstinaServiceDecision(False, "service_has_no_result")
        if service_result_id not in known_ids:
            return IstinaServiceDecision(False, "service_result_not_in_local_history")

        candidate_groups = IstinaDisambiguationClient.parse_candidate_groups(response)
        first_group = candidate_groups[0] if candidate_groups else []
        result_candidates = [
            candidate for candidate in first_group if candidate.id == service_result_id
        ]
        if len(result_candidates) != 1:
            return IstinaServiceDecision(False, "service_result_not_unique_in_candidates")

        candidate = result_candidates[0]
        if (
            not math.isfinite(candidate.name_similarity)
            or candidate.name_similarity < min_name_similarity
        ):
            return IstinaServiceDecision(False, "service_name_similarity_below_threshold")

        return IstinaServiceDecision(True, "known_author_service_fallback", candidate)


def istina_author_record_from_export(
    article: Dict[str, Any],
    author: Dict[str, Any],
    fallback_position: Optional[int] = None,
    fallback_article_index: Optional[int] = None,
) -> AuthorRecord:
    """Convert one ISTINA exported author row into the local framework record.

    The conversion is deliberately lossless and local: it preserves the
    exported name where available, adds same-publication coauthor names as
    context, and does not call or trust the remote ISTINA service.
    """

    article_id = _article_identifier(article)
    position = author.get("position") or author.get("author_position") or fallback_position
    author_id = author.get("author_id") or author.get("id")
    record_suffix = str(position or author_id or "unknown")
    record_id_parts = ["istina", article_id]
    if fallback_article_index is not None:
        record_id_parts.append(str(fallback_article_index))
    if fallback_article_index is not None and fallback_position is not None:
        record_suffix = f"{record_suffix}:{fallback_position}"
    record_id_parts.append(record_suffix)
    current_name = _exported_author_name(author)

    coauthors: List[str] = []
    for other_index, other in enumerate(article.get("authors") or [], start=1):
        other_position = other.get("position") or other.get("author_position") or other_index
        if fallback_position is not None and other_index == fallback_position:
            continue
        if fallback_position is None and position is not None and other_position == position:
            continue
        if position is None and author_id and (other.get("author_id") or other.get("id")) == author_id:
            continue
        other_name = _exported_author_name(other)
        if other_name and other_name != current_name:
            coauthors.append(other_name)

    return AuthorRecord(
        record_id=":".join(record_id_parts),
        name=current_name,
        coauthors=coauthors,
        journal=article.get("journal") or article.get("venue") or None,
        publication_title=article.get("title") or None,
        year=article.get("year"),
        affiliation=author.get("affiliation") or None,
        source="istina_export",
    )


def iter_istina_author_records(articles: Iterable[Dict[str, Any]]) -> Iterator[AuthorRecord]:
    """Yield local framework records from an ISTINA publication export."""

    for fallback_article_index, article in enumerate(articles, start=1):
        for fallback_position, author in enumerate(article.get("authors") or [], start=1):
            record = istina_author_record_from_export(
                article,
                author,
                fallback_position,
                fallback_article_index,
            )
            if record.name:
                yield record


def needs_short_family_middle_guard(last_name: str, first_name: str, middle_name: str) -> bool:
    """Return True for the known ISTINA short-family-name parse risk."""

    last_name = (last_name or "").strip()
    first_name = (first_name or "").strip()
    middle_name = (middle_name or "").strip()
    compact_last_name = "".join(ch for ch in last_name if ch.isalpha())
    return bool(last_name and first_name and not middle_name and len(compact_last_name) <= 2)
