"""Leakage-safe loader for the public Crossref--ORCID S2AND replay.

The loader joins three public sources while keeping identity labels outside
the model feature rows:

* the author export supplies structured target names, year, affiliation and
  label-only ORCID;
* the Crossref article-author map supplies source order and complete coauthors;
* the cached Semantic Scholar response supplies paper text and SPECTER2.

The synthetic ``original_name`` export field and article-map ORCID values are
never read.  Target position is resolved from structured names only, with
ambiguous matches rejected rather than guessed.
"""

from __future__ import annotations

from array import array
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import (  # noqa: E402
    iter_json_object_items,
    iter_json_records,
)
from experiments.audit_s2and_replay_complexity import canonical_block  # noqa: E402
from experiments.semantic_scholar_specter_enrichment import (  # noqa: E402
    _read_cache,
    normalize_doi,
)


SPECTER2_DIMENSION = 768


def _text(value: Any) -> str:
    return str(value or "").strip()


def _name_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", _text(value)).casefold()
    characters = [
        character if unicodedata.category(character)[0] in {"L", "N"} else " "
        for character in normalized
    ]
    return " ".join("".join(characters).split())


def _stable_key(*values: str) -> bytes:
    return hashlib.sha256("\0".join(values).encode("utf-8")).digest()


@dataclass(frozen=True, slots=True)
class ObservedPaperAuthor:
    given_key: str
    family_key: str
    display_name: str


@dataclass(frozen=True, slots=True)
class PaperContext:
    doi: str
    title: str
    abstract: str
    journal_name: str
    venue: str
    embedding: array


@dataclass(frozen=True, slots=True)
class ReplayMention:
    doi: str
    identity: str
    first: str
    last: str
    affiliation: str
    year: int
    author_position: int
    paper_authors: tuple[ObservedPaperAuthor, ...]
    paper: PaperContext

    @property
    def block(self) -> str:
        return canonical_block(self.first, self.last)

    def adapter_row(self, *, include_history_label: bool) -> dict[str, Any]:
        row: dict[str, Any] = {
            "doi": self.doi,
            "firstname": self.first,
            "lastname": self.last,
            "affiliation": self.affiliation,
            "year": self.year,
            "author_position": self.author_position,
            "paper_authors": [
                {"position": position, "author_name": author.display_name}
                for position, author in enumerate(self.paper_authors)
            ],
            "title": self.paper.title,
            "abstract": self.paper.abstract,
            "journal_name": self.paper.journal_name,
            "venue": self.paper.venue,
        }
        if include_history_label:
            row["gold_author_id"] = self.identity
        return row


@dataclass(frozen=True)
class ReplayCorpus:
    blocks: dict[str, tuple[tuple[ReplayMention, ...], tuple[ReplayMention, ...]]]
    global_history_identities: frozenset[str]
    coverage: dict[str, int]

    @property
    def history_count(self) -> int:
        return sum(len(history) for history, _query in self.blocks.values())

    @property
    def query_count(self) -> int:
        return sum(len(query) for _history, query in self.blocks.values())


def _structured_author(item: Mapping[str, Any]) -> ObservedPaperAuthor | None:
    # The map's ORCID and unstructured name are deliberately not accessed.
    given = _text(item.get("given"))
    family = _text(item.get("family"))
    given_key = _name_key(given)
    family_key = _name_key(family)
    display = " ".join(part for part in (given, family) if part)
    if not given_key or not family_key or not display:
        return None
    return ObservedPaperAuthor(given_key, family_key, display)


def load_article_authors(
    path: Path,
) -> tuple[dict[str, tuple[ObservedPaperAuthor, ...]], dict[str, int]]:
    papers: dict[str, tuple[ObservedPaperAuthor, ...]] = {}
    invalid_keys: set[str] = set()
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_article_id, raw_authors in iter_json_object_items(handle):
            counts["map_entries"] += 1
            article_id = _text(raw_article_id).casefold()
            if not article_id or not isinstance(raw_authors, list) or not raw_authors:
                counts["invalid_entries"] += 1
                if article_id:
                    invalid_keys.add(article_id)
                continue
            authors: list[ObservedPaperAuthor] = []
            complete = True
            for raw_author in raw_authors:
                if not isinstance(raw_author, Mapping):
                    complete = False
                    break
                author = _structured_author(raw_author)
                if author is None:
                    complete = False
                    break
                authors.append(author)
            if not complete:
                counts["incomplete_author_lists"] += 1
                invalid_keys.add(article_id)
                continue
            value = tuple(authors)
            existing = papers.get(article_id)
            if existing is not None and existing != value:
                counts["conflicting_duplicate_keys"] += 1
                invalid_keys.add(article_id)
                continue
            if existing is not None:
                counts["identical_duplicate_keys"] += 1
            else:
                papers[article_id] = value

    for key in invalid_keys:
        papers.pop(key, None)
    counts["usable_papers"] = len(papers)
    return papers, dict(counts)


def _mapping_name(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    return _text(value.get("name"))


def _paper_context(row: Mapping[str, Any]) -> PaperContext | None:
    external_ids = row.get("externalIds")
    if not isinstance(external_ids, Mapping):
        return None
    doi = normalize_doi(external_ids.get("DOI"))
    embedding = row.get("embedding")
    vector = embedding.get("vector") if isinstance(embedding, Mapping) else None
    title = _text(row.get("title"))
    if not doi or not title or not isinstance(vector, list) or len(vector) != SPECTER2_DIMENSION:
        return None
    values = array("f")
    try:
        values.fromlist([float(value) for value in vector])
    except (TypeError, ValueError, OverflowError):
        return None
    if len(values) != SPECTER2_DIMENSION or not all(math.isfinite(value) for value in values):
        return None
    journal = _mapping_name(row.get("journal"))
    publication_venue = _mapping_name(row.get("publicationVenue"))
    venue = _text(row.get("venue")) or publication_venue or journal
    return PaperContext(
        doi=doi,
        title=title,
        abstract=_text(row.get("abstract")),
        journal_name=journal or publication_venue or venue,
        venue=venue,
        embedding=values,
    )


def load_paper_contexts(
    cache_dir: Path,
) -> tuple[dict[str, PaperContext], dict[str, int]]:
    contexts: dict[str, PaperContext] = {}
    counts: Counter[str] = Counter()
    seen_digests: set[str] = set()
    paths = sorted(cache_dir.glob("batch_*.json.gz")) + sorted(
        cache_dir.glob("batch_*.json")
    )
    for path in paths:
        cache = _read_cache(path)
        digest = _text(cache.get("doi_digest"))
        if not digest or digest in seen_digests:
            counts["duplicate_cache_batches"] += 1
            continue
        seen_digests.add(digest)
        rows = cache.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"invalid Semantic Scholar cache rows in {path.name}")
        counts["cache_rows"] += len(rows)
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            context = _paper_context(raw)
            if context is None:
                continue
            if context.doi in contexts:
                counts["duplicate_dois"] += 1
                continue
            contexts[context.doi] = context
    counts["usable_contexts"] = len(contexts)
    return contexts, dict(counts)


def resolve_author_position(
    first: str,
    last: str,
    paper_authors: tuple[ObservedPaperAuthor, ...],
) -> tuple[int | None, str]:
    first_key = _name_key(first)
    last_key = _name_key(last)
    exact = [
        index
        for index, author in enumerate(paper_authors)
        if author.given_key == first_key and author.family_key == last_key
    ]
    if len(exact) == 1:
        return exact[0], "exact"
    if len(exact) > 1:
        return None, "ambiguous_exact"

    def compatible_given(observed: str) -> bool:
        if not first_key or not observed:
            return False
        first_tokens = first_key.split()
        observed_tokens = observed.split()
        if first_tokens[0] == observed_tokens[0]:
            return True
        if len(first_tokens[0]) == 1 and observed_tokens[0].startswith(first_tokens[0]):
            return True
        if len(observed_tokens[0]) == 1 and first_tokens[0].startswith(observed_tokens[0]):
            return True
        return False

    compatible = [
        index
        for index, author in enumerate(paper_authors)
        if author.family_key == last_key and compatible_given(author.given_key)
    ]
    if len(compatible) == 1:
        return compatible[0], "unique_given_prefix"
    if len(compatible) > 1:
        return None, "ambiguous_prefix"
    return None, "no_structured_match"


def load_replay_corpus(
    authors_path: Path,
    article_authors_path: Path,
    cache_dir: Path,
    *,
    cutoff_year: int,
) -> ReplayCorpus:
    article_authors, map_counts = load_article_authors(article_authors_path)
    contexts, context_counts = load_paper_contexts(cache_dir)
    history: dict[str, list[ReplayMention]] = defaultdict(list)
    query: dict[str, list[ReplayMention]] = defaultdict(list)
    history_identities: set[str] = set()
    counts: Counter[str] = Counter()
    counts.update({f"article_map_{key}": value for key, value in map_counts.items()})
    counts.update({f"context_{key}": value for key, value in context_counts.items()})
    seen_mentions: set[tuple[str, str, int]] = set()
    paper_sides: dict[str, int] = {}

    with authors_path.open("r", encoding="utf-8-sig") as handle:
        for raw in iter_json_records(handle):
            counts["author_rows"] += 1
            if not isinstance(raw, Mapping):
                continue
            # Explicit whitelist: original_name is not read or propagated.
            first = _text(raw.get("firstname"))
            last = _text(raw.get("lastname"))
            identity = _text(raw.get("orcid"))
            doi = normalize_doi(raw.get("doi"))
            article_id = _text(raw.get("article_id")).casefold()
            affiliation = _text(raw.get("affiliation"))
            try:
                year = int(raw.get("year"))
            except (TypeError, ValueError):
                counts["missing_or_invalid_required_fields"] += 1
                continue
            if not first or not last or not identity or not doi or not article_id:
                counts["missing_or_invalid_required_fields"] += 1
                continue
            paper = contexts.get(doi)
            if paper is None:
                counts["missing_specter2_context"] += 1
                continue
            paper_authors = article_authors.get(article_id)
            if paper_authors is None:
                counts["missing_complete_article_authors"] += 1
                continue
            position, rule = resolve_author_position(first, last, paper_authors)
            counts[f"position_{rule}"] += 1
            if position is None:
                continue
            mention_key = (doi, identity, position)
            if mention_key in seen_mentions:
                counts["duplicate_mentions"] += 1
                continue
            seen_mentions.add(mention_key)
            mention = ReplayMention(
                doi=doi,
                identity=identity,
                first=first,
                last=last,
                affiliation=affiliation,
                year=year,
                author_position=position,
                paper_authors=paper_authors,
                paper=paper,
            )
            side = 0 if year <= cutoff_year else 1
            previous_side = paper_sides.setdefault(doi, side)
            if previous_side != side:
                raise ValueError("temporal paper leakage detected")
            if side == 0:
                history[mention.block].append(mention)
                history_identities.add(identity)
                counts["history_mentions"] += 1
            else:
                query[mention.block].append(mention)
                counts["query_mentions"] += 1

    blocks: dict[str, tuple[tuple[ReplayMention, ...], tuple[ReplayMention, ...]]] = {}
    for block in set(history).union(query):
        history_rows = tuple(
            sorted(
                history.get(block, []),
                key=lambda row: _stable_key(row.doi, row.identity, str(row.author_position)),
            )
        )
        query_rows = tuple(
            sorted(
                query.get(block, []),
                key=lambda row: _stable_key(row.doi, row.identity, str(row.author_position)),
            )
        )
        blocks[block] = (history_rows, query_rows)
    counts["blocks"] = len(blocks)
    counts["query_blocks"] = sum(bool(query_rows) for _history, query_rows in blocks.values())
    return ReplayCorpus(
        blocks=blocks,
        global_history_identities=frozenset(history_identities),
        coverage=dict(counts),
    )


def deterministic_query_blocks(corpus: ReplayCorpus) -> list[str]:
    return sorted(
        (block for block, (_history, query) in corpus.blocks.items() if query),
        key=lambda block: (_stable_key(block), block),
    )


def adapter_inputs(
    corpus: ReplayCorpus,
    blocks: Iterable[str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[ReplayMention],
    dict[str, array],
]:
    history_rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    query_labels: list[ReplayMention] = []
    embeddings: dict[str, array] = {}
    for block in blocks:
        history, query = corpus.blocks[block]
        for mention in history:
            history_rows.append(mention.adapter_row(include_history_label=True))
            embeddings.setdefault(mention.doi, mention.paper.embedding)
        for mention in query:
            # The query feature row physically contains no identity field.
            query_rows.append(mention.adapter_row(include_history_label=False))
            query_labels.append(mention)
            embeddings.setdefault(mention.doi, mention.paper.embedding)
    return history_rows, query_rows, query_labels, embeddings
