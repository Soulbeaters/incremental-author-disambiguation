"""Leakage-safe textual evidence between a paper and an author profile."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import html
import math
import re
from typing import Any, Iterable, Mapping


TOKEN_RE = re.compile(r"[^\W\d_]{3,}", flags=re.UNICODE)
TAG_RE = re.compile(r"<[^>]+>")


def _tokens(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    clean = html.unescape(TAG_RE.sub(" ", str(value or ""))).casefold()
    return tuple(TOKEN_RE.findall(clean))


def _venue_key(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if item), "")
    return " ".join(_tokens(value))


@dataclass(frozen=True)
class TopicEvidence:
    profile_cosine: float
    max_paper_cosine: float
    max_title_jaccard: float
    venue_match: float
    log_profile_papers: float
    query_has_abstract: float

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.profile_cosine,
            self.max_paper_cosine,
            self.max_title_jaccard,
            self.venue_match,
            self.log_profile_papers,
            self.query_has_abstract,
        )


class TopicProfileIndex:
    """Historical TF-IDF profiles; query documents never affect the IDF."""

    FEATURE_NAMES = (
        "topic_profile_cosine",
        "topic_max_paper_cosine",
        "topic_max_title_jaccard",
        "topic_venue_match",
        "topic_log_profile_papers",
        "topic_query_has_abstract",
    )

    def __init__(
        self,
        author_papers: Mapping[str, tuple[str, ...]],
        paper_terms: Mapping[str, Counter[str]],
        title_terms: Mapping[str, frozenset[str]],
        paper_venues: Mapping[str, str],
        idf: Mapping[str, float],
    ) -> None:
        self.author_papers = dict(author_papers)
        self.paper_terms = dict(paper_terms)
        self.title_terms = dict(title_terms)
        self.paper_venues = dict(paper_venues)
        self.idf = dict(idf)
        self.author_terms: dict[str, Counter[str]] = {}
        for author_id, paper_ids in self.author_papers.items():
            combined: Counter[str] = Counter()
            for paper_id in paper_ids:
                combined.update(self.paper_terms.get(paper_id, {}))
            self.author_terms[author_id] = combined

    @classmethod
    def from_history(
        cls,
        history_mentions: Iterable[Mapping[str, Any]],
        metadata_by_paper: Mapping[str, Mapping[str, Any]],
    ) -> "TopicProfileIndex":
        author_papers: dict[str, set[str]] = defaultdict(set)
        for mention in history_mentions:
            author_id = str(mention.get("gold_author_id") or mention.get("author_id") or "")
            paper_id = str(mention.get("article_id") or mention.get("doi") or "").casefold()
            if author_id and paper_id and paper_id in metadata_by_paper:
                author_papers[author_id].add(paper_id)

        used_papers = sorted(set().union(*author_papers.values())) if author_papers else []
        paper_terms: dict[str, Counter[str]] = {}
        title_terms: dict[str, frozenset[str]] = {}
        paper_venues: dict[str, str] = {}
        document_frequency: Counter[str] = Counter()
        for paper_id in used_papers:
            metadata = metadata_by_paper[paper_id]
            title = _tokens(metadata.get("title"))
            abstract = _tokens(metadata.get("abstract"))
            terms = Counter((*title, *abstract))
            paper_terms[paper_id] = terms
            title_terms[paper_id] = frozenset(title)
            paper_venues[paper_id] = _venue_key(metadata.get("container-title"))
            document_frequency.update(terms.keys())
        total = len(used_papers)
        idf = {
            token: math.log((total + 1.0) / (frequency + 1.0)) + 1.0
            for token, frequency in document_frequency.items()
        }
        return cls(
            {author_id: tuple(sorted(papers)) for author_id, papers in author_papers.items()},
            paper_terms,
            title_terms,
            paper_venues,
            idf,
        )

    def _cosine(self, left: Counter[str], right: Counter[str]) -> float:
        shared = left.keys() & right.keys()
        numerator = sum(
            left[token] * right[token] * self.idf.get(token, 1.0) ** 2
            for token in shared
        )
        left_norm = math.sqrt(sum(
            count * count * self.idf.get(token, 1.0) ** 2
            for token, count in left.items()
        ))
        right_norm = math.sqrt(sum(
            count * count * self.idf.get(token, 1.0) ** 2
            for token, count in right.items()
        ))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def evidence(
        self,
        author_id: str,
        query_metadata: Mapping[str, Any],
    ) -> TopicEvidence:
        paper_ids = self.author_papers.get(str(author_id), ())
        title = frozenset(_tokens(query_metadata.get("title")))
        abstract = _tokens(query_metadata.get("abstract"))
        query_terms = Counter((*title, *abstract))
        venue = _venue_key(query_metadata.get("container-title"))
        profile_cosine = self._cosine(
            query_terms, self.author_terms.get(str(author_id), Counter())
        )
        paper_cosines = [
            self._cosine(query_terms, self.paper_terms[paper_id])
            for paper_id in paper_ids
        ]
        title_overlaps = []
        for paper_id in paper_ids:
            historical = self.title_terms.get(paper_id, frozenset())
            union = title | historical
            title_overlaps.append(len(title & historical) / len(union) if union else 0.0)
        return TopicEvidence(
            profile_cosine=profile_cosine,
            max_paper_cosine=max(paper_cosines, default=0.0),
            max_title_jaccard=max(title_overlaps, default=0.0),
            venue_match=float(bool(venue) and any(
                self.paper_venues.get(paper_id) == venue for paper_id in paper_ids
            )),
            log_profile_papers=math.log1p(len(paper_ids)),
            query_has_abstract=float(bool(abstract)),
        )


__all__ = ["TopicEvidence", "TopicProfileIndex"]
