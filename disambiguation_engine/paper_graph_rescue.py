"""Conservative paper-level rescue using historical coauthor relations.

The base pipeline remains authoritative.  This module only proposes candidates
for unresolved mentions, and exposes graph support so a separately frozen risk
threshold can decide whether a proposal is safe enough to accept.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from heapq import nlargest
import math
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PaperGraphPrediction:
    author_id: str
    support: float


@dataclass(frozen=True)
class HistoricalCoauthorGraph:
    edge_counts: Mapping[tuple[str, str], int]
    edge_years: Mapping[tuple[str, str], tuple[int, ...]]
    profile_sizes: Mapping[str, int]

    @classmethod
    def from_mentions(
        cls,
        mentions: Iterable[Mapping[str, Any]],
    ) -> "HistoricalCoauthorGraph":
        authors_by_paper: dict[str, set[str]] = defaultdict(set)
        year_by_paper: dict[str, int] = {}
        profile_sizes: Counter[str] = Counter()
        for mention in mentions:
            author_id = str(
                mention.get("gold_author_id")
                or mention.get("author_id")
                or ""
            )
            paper_id = str(
                mention.get("article_id")
                or mention.get("doi")
                or ""
            )
            if not author_id:
                continue
            profile_sizes[author_id] += 1
            if paper_id:
                authors_by_paper[paper_id].add(author_id)
                try:
                    year = int(mention.get("year"))
                except (TypeError, ValueError):
                    year = 0
                if year:
                    year_by_paper[paper_id] = year

        edges: Counter[tuple[str, str]] = Counter()
        edge_years: dict[tuple[str, str], list[int]] = defaultdict(list)
        for paper_id, author_ids in authors_by_paper.items():
            ordered = sorted(author_ids)
            for left_index, left in enumerate(ordered):
                for right in ordered[left_index + 1:]:
                    edge = (left, right)
                    edges[edge] += 1
                    if paper_id in year_by_paper:
                        edge_years[edge].append(year_by_paper[paper_id])
        return cls(
            dict(edges),
            {edge: tuple(sorted(years)) for edge, years in edge_years.items()},
            dict(profile_sizes),
        )

    def support(
        self,
        left: str,
        right: str,
        query_year: int | None = None,
        half_life_years: float | None = None,
    ) -> float:
        if not left or not right or left == right:
            return 0.0
        edge = tuple(sorted((left, right)))
        count = int(self.edge_counts.get(edge, 0))
        if not count:
            return 0.0
        if query_year is None or half_life_years is None:
            return math.log1p(count)
        if half_life_years <= 0.0:
            raise ValueError("half_life_years must be positive")
        years = self.edge_years.get(edge, ())
        if not years:
            return math.log1p(count)
        weight = sum(
            0.5 ** (max(0, query_year - year) / half_life_years)
            for year in years
        )
        return math.log1p(weight)


def _candidate_ids(
    record: Mapping[str, Any],
    min_name_similarity: float,
) -> list[str]:
    if "graph_candidate_ids" in record:
        return sorted({
            str(author_id)
            for author_id in record.get("graph_candidate_ids") or []
            if author_id not in (None, "")
        })
    return sorted({
        str(candidate.get("author_id") or "")
        for candidate in record.get("topk") or []
        if candidate.get("author_id")
        and float(
            (candidate.get("comparisons") or {}).get("name_sim") or 0.0
        ) >= min_name_similarity
    })


def predict_paper_graph(
    records: Sequence[Mapping[str, Any]],
    graph: HistoricalCoauthorGraph,
    beam_size: int = 256,
    min_name_similarity: float = 0.0,
    time_decay_half_life_years: float | None = None,
) -> dict[int, PaperGraphPrediction]:
    """Return deterministic graph proposals indexed by paper-local position.

    Existing base MERGE decisions are fixed.  A historical identity may occur
    at most once on the incoming paper, matching the old ISTINA paper-level
    assignment constraint.
    """

    years = []
    for record in records:
        try:
            year = int(record.get("year"))
        except (TypeError, ValueError):
            year = 0
        if year:
            years.append(year)
    query_year = max(years) if years else None
    fixed = {
        position: str(record.get("author_id") or "")
        for position, record in enumerate(records)
        if record.get("decision") == "merge" and record.get("author_id")
    }
    fixed_ids = frozenset(fixed.values())
    fixed_score = sum(
        graph.support(left, right, query_year, time_decay_half_life_years)
        for left_index, left in enumerate(sorted(fixed_ids))
        for right in sorted(fixed_ids)[left_index + 1:]
    )
    beams: list[tuple[float, dict[int, str], frozenset[str]]] = [
        (fixed_score, dict(fixed), fixed_ids)
    ]
    unresolved = sorted(
        (
            (position, _candidate_ids(record, min_name_similarity))
            for position, record in enumerate(records)
            if position not in fixed
        ),
        key=lambda item: (len(item[1]) if item[1] else math.inf, item[0]),
    )
    for position, candidates in unresolved:
        if not candidates:
            continue
        next_beams: list[tuple[float, dict[int, str], frozenset[str]]] = []
        for score, assignment, used_ids in beams:
            for author_id in candidates:
                if author_id in used_ids:
                    continue
                increment = 0.01 * math.log1p(
                    int(graph.profile_sizes.get(author_id, 0))
                )
                increment += sum(
                    graph.support(
                        author_id,
                        selected,
                        query_year,
                        time_decay_half_life_years,
                    )
                    for selected in assignment.values()
                )
                updated = dict(assignment)
                updated[position] = author_id
                next_beams.append(
                    (score + increment, updated, used_ids | {author_id})
                )
        if next_beams:
            beams = nlargest(
                beam_size,
                next_beams,
                key=lambda item: (
                    item[0],
                    tuple(sorted(item[1].items())),
                ),
            )

    assignment = max(
        beams,
        key=lambda item: (item[0], tuple(sorted(item[1].items()))),
    )[1]
    predictions: dict[int, PaperGraphPrediction] = {}
    for position, author_id in assignment.items():
        if position in fixed:
            continue
        support = sum(
            graph.support(
                author_id,
                selected,
                query_year,
                time_decay_half_life_years,
            )
            for other_position, selected in assignment.items()
            if other_position != position
        )
        predictions[position] = PaperGraphPrediction(author_id, support)
    return predictions


def predict_graph_by_paper(
    history_mentions: Iterable[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    min_name_similarity: float = 0.0,
    time_decay_half_life_years: float | None = None,
    historical_graph: HistoricalCoauthorGraph | None = None,
) -> dict[int, PaperGraphPrediction]:
    """Return graph proposals indexed by global record position."""

    graph = (
        historical_graph
        or HistoricalCoauthorGraph.from_mentions(history_mentions)
    )
    positions_by_paper: dict[str, list[int]] = defaultdict(list)
    for position, record in enumerate(records):
        positions_by_paper[str(record.get("article_id") or position)].append(position)
    predictions: dict[int, PaperGraphPrediction] = {}
    for positions in positions_by_paper.values():
        paper_records = [records[position] for position in positions]
        for local_position, prediction in predict_paper_graph(
            paper_records,
            graph,
            min_name_similarity=min_name_similarity,
            time_decay_half_life_years=time_decay_half_life_years,
        ).items():
            predictions[positions[local_position]] = prediction
    return predictions


__all__ = [
    "HistoricalCoauthorGraph",
    "PaperGraphPrediction",
    "predict_graph_by_paper",
    "predict_paper_graph",
]
