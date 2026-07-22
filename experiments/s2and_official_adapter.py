"""Leakage-safe intermediate adapter for the official S2AND baseline.

The module builds the service-shaped JSON object accepted by S2AND's official
``convert_service_json_to_arrow`` route.  It deliberately does not write files
or invoke S2AND.  Arrow conversion and inference remain separate, auditable
steps once the enriched paper context and SPECTER2 vectors are available.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


SPECTER2_DIMENSION = 768
FORBIDDEN_INPUT_FIELDS = frozenset({"original_name"})


@dataclass(frozen=True)
class S2ANDAdapterResult:
    payload: dict[str, Any]
    history_signature_ids: tuple[str, ...]
    query_signature_ids: tuple[str, ...]
    coverage: dict[str, int]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _paper_key(row: Mapping[str, Any]) -> str:
    value = row.get("article_id") or row.get("doi") or row.get("paper_id")
    key = _text(value).casefold()
    if not key:
        raise ValueError("S2AND adapter row is missing article_id/doi/paper_id")
    return key


def _paper_id(key: str) -> int:
    """Map a source paper key to a stable positive signed-63-bit integer."""

    value = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    return (value & ((1 << 63) - 1)) or 1


def _seed_component(identity: str) -> str:
    digest = hashlib.sha256(("s2and-history-seed\0" + identity).encode("utf-8")).hexdigest()
    return "seed:" + digest[:24]


def _structured_name(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    first = _text(row.get("firstname") or row.get("first_name"))
    middle = _text(row.get("middlename") or row.get("middle_name"))
    last = _text(row.get("lastname") or row.get("last_name"))
    if not first or not last:
        raise ValueError("S2AND adapter requires structured first and last name")
    full = " ".join(part for part in (first, middle, last) if part)
    return first, middle, last, full


def _affiliations(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("affiliations")
    if raw is None:
        raw = row.get("affiliation")
    if isinstance(raw, str) or raw is None:
        values = [raw]
    elif isinstance(raw, Sequence):
        values = list(raw)
    else:
        raise TypeError("affiliations must be a string or sequence")
    return sorted({_text(value) for value in values if _text(value)})


def _paper_authors(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("paper_authors")
    if isinstance(raw, str) or not isinstance(raw, Sequence) or not raw:
        raise ValueError("S2AND adapter requires the complete observed paper_authors list")
    authors: list[dict[str, Any]] = []
    positions: set[int] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise TypeError("paper_authors entries must be mappings")
        try:
            position = int(item["position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("paper_authors requires an integer source position") from exc
        name = _text(item.get("author_name") or item.get("name"))
        if position < 0 or not name or position in positions:
            raise ValueError("paper_authors positions must be unique, non-negative, and named")
        positions.add(position)
        authors.append({"position": position, "author_name": name})
    return sorted(authors, key=lambda item: (item["position"], item["author_name"]))


def _history_identity(row: Mapping[str, Any]) -> str:
    identity = _text(row.get("gold_author_id") or row.get("author_id") or row.get("orcid"))
    if not identity:
        raise ValueError("history rows require a verified identity for seed construction")
    return identity


def _assert_input_boundary(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        leaked = FORBIDDEN_INPUT_FIELDS.intersection(row)
        if leaked:
            raise ValueError(f"forbidden synthetic fields at S2AND boundary: {sorted(leaked)}")


def build_s2and_service_payload(
    history_rows: Sequence[Mapping[str, Any]],
    query_rows: Sequence[Mapping[str, Any]],
    *,
    paper_embeddings: Mapping[str, Sequence[float]],
) -> S2ANDAdapterResult:
    """Build an official-converter payload without exposing query labels.

    ``paper_embeddings`` is keyed by the normalized source paper id/DOI and
    must contain a 768-dimensional SPECTER2 vector for every paper.  Query gold
    fields may be present in the caller's private records, but this function
    never reads or copies them.
    """

    history = list(history_rows)
    queries = list(query_rows)
    _assert_input_boundary(history)
    _assert_input_boundary(queries)

    history_papers = {_paper_key(row) for row in history}
    query_papers = {_paper_key(row) for row in queries}
    overlap = history_papers.intersection(query_papers)
    if overlap:
        raise ValueError(f"history/query paper leakage detected ({len(overlap)} paper(s))")

    signatures: dict[str, dict[str, Any]] = {}
    papers: dict[str, dict[str, Any]] = {}
    embeddings: dict[str, list[float]] = {}
    seed_members: dict[str, list[str]] = defaultdict(list)
    history_signature_ids: list[str] = []
    query_signature_ids: list[str] = []

    coverage = {
        "history_signatures": len(history),
        "query_signatures": len(queries),
        "papers": 0,
        "papers_with_title": 0,
        "papers_with_abstract": 0,
        "signatures_with_affiliation": 0,
        "papers_with_specter2": 0,
    }

    seen_paper_ids: dict[int, str] = {}

    def add_row(row: Mapping[str, Any], phase: str, index: int) -> str:
        key = _paper_key(row)
        numeric_paper_id = _paper_id(key)
        previous_key = seen_paper_ids.setdefault(numeric_paper_id, key)
        if previous_key != key:
            raise ValueError("stable paper-id hash collision")

        first, middle, last, full_name = _structured_name(row)
        try:
            author_position = int(row["author_position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("S2AND adapter requires zero-based author_position") from exc
        if author_position < 0:
            raise ValueError("author_position must be non-negative")

        affiliations = _affiliations(row)
        signature_id = f"{phase}:{index}"
        block = first[0].casefold() + " " + last.casefold()
        signatures[signature_id] = {
            "author_info": {
                "first": first,
                "middle": middle or None,
                "last": last,
                "suffix": None,
                "position": author_position,
                "email": None,
                "affiliations": affiliations,
                "block": block,
                "estimated_ethnicity": None,
                "estimated_gender": None,
                "given_block": block,
            },
            "signature_id": signature_id,
            "given_name": full_name,
            "paper_id": numeric_paper_id,
            # ORCID/identity is evaluation-only.  Even history signatures use
            # opaque seed components instead of S2AND's sourced-author field.
            "sourced_author_ids": [],
            "sourced_author_source": None,
        }
        coverage["signatures_with_affiliation"] += int(bool(affiliations))

        authors = _paper_authors(row)
        if author_position not in {item["position"] for item in authors}:
            raise ValueError("author_position is absent from the complete paper_authors list")
        paper = {
            "paper_id": numeric_paper_id,
            "title": _text(row.get("title")),
            "abstract": _text(row.get("abstract")),
            "journal_name": _text(row.get("journal_name") or row.get("journal")) or None,
            "venue": _text(row.get("venue")) or None,
            "year": int(row["year"]) if row.get("year") not in (None, "") else None,
            "sources": ["Crossref"],
            "fields_of_study": [],
            "authors": authors,
            "references": [],
        }
        paper_key_text = str(numeric_paper_id)
        existing_paper = papers.get(paper_key_text)
        if existing_paper is not None and existing_paper != paper:
            raise ValueError(f"inconsistent metadata for paper {key!r}")
        if existing_paper is None:
            papers[paper_key_text] = paper
            coverage["papers"] += 1
            coverage["papers_with_title"] += int(bool(paper["title"]))
            coverage["papers_with_abstract"] += int(bool(paper["abstract"]))

            vector = paper_embeddings.get(key)
            if vector is None:
                raise ValueError(f"missing SPECTER2 embedding for paper {key!r}")
            normalized_vector = [float(value) for value in vector]
            if len(normalized_vector) != SPECTER2_DIMENSION:
                raise ValueError(
                    f"SPECTER2 embedding for {key!r} has dimension "
                    f"{len(normalized_vector)}; expected {SPECTER2_DIMENSION}"
                )
            embeddings[paper_key_text] = normalized_vector
            coverage["papers_with_specter2"] += 1
        return signature_id

    for index, row in enumerate(history):
        signature_id = add_row(row, "history", index)
        history_signature_ids.append(signature_id)
        seed_members[_seed_component(_history_identity(row))].append(signature_id)

    for index, row in enumerate(queries):
        signature_id = add_row(row, "query", index)
        query_signature_ids.append(signature_id)

    payload = {
        "signatures": signatures,
        "papers": papers,
        "paper_embeddings": embeddings,
        "cluster_seeds": {
            "require": {
                component: sorted(member_ids)
                for component, member_ids in sorted(seed_members.items())
            },
            "disallow": [],
        },
        "altered_cluster_signatures": [],
    }
    return S2ANDAdapterResult(
        payload=payload,
        history_signature_ids=tuple(history_signature_ids),
        query_signature_ids=tuple(query_signature_ids),
        coverage=coverage,
    )
