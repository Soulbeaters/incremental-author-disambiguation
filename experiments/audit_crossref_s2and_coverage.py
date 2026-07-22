"""Stream an aggregate-only S2AND field-coverage audit over Crossref JSON.

The source files are large top-level JSON arrays.  This module uses only the
standard library, never prints record values, and retains only counters plus
normalized DOI keys needed for aggregate join coverage.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import chain
import json
from pathlib import Path
import time
from typing import Any, Iterator, Mapping, TextIO


CHUNK_SIZE = 64 * 1024


def _iter_collection_segments(
    handle: TextIO,
    *,
    opening: str,
    closing: str,
    label: str,
    chunk_size: int,
) -> Iterator[str]:
    """Yield encoded top-level members from one JSON array or object."""

    started = False
    finished = False
    in_string = False
    escaped = False
    nested_depth = 0
    item_parts: list[str] = []

    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            break
        index = 0
        if not started:
            while index < len(chunk) and chunk[index].isspace():
                index += 1
            if index == len(chunk):
                continue
            if chunk[index] != opening:
                raise ValueError(f"expected a top-level JSON {label}")
            started = True
            index += 1

        segment_start = index
        while index < len(chunk):
            character = chunk[index]
            if finished:
                if not character.isspace():
                    raise ValueError(f"unexpected content after top-level JSON {label}")
                index += 1
                segment_start = index
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
            elif character == '"':
                in_string = True
            elif character in "{[":
                nested_depth += 1
            elif character in "}]":
                if character == closing and nested_depth == 0:
                    item_parts.append(chunk[segment_start:index])
                    item_text = "".join(item_parts).strip()
                    if item_text:
                        yield item_text
                    item_parts.clear()
                    finished = True
                    segment_start = index + 1
                elif nested_depth <= 0:
                    raise ValueError(f"unbalanced JSON {label} member")
                else:
                    nested_depth -= 1
            elif character == "," and nested_depth == 0:
                item_parts.append(chunk[segment_start:index])
                item_text = "".join(item_parts).strip()
                if not item_text:
                    raise ValueError(f"empty JSON {label} member")
                yield item_text
                item_parts.clear()
                segment_start = index + 1
            index += 1
        if not finished and segment_start < len(chunk):
            item_parts.append(chunk[segment_start:])

    if not started:
        raise ValueError(f"empty JSON input; expected a top-level {label}")
    if not finished:
        raise ValueError(f"unterminated top-level JSON {label}")


def iter_json_array(handle: TextIO, chunk_size: int = CHUNK_SIZE) -> Iterator[Any]:
    """Yield items from one top-level JSON array without loading it in memory."""

    for encoded in _iter_collection_segments(
        handle,
        opening="[",
        closing="]",
        label="array",
        chunk_size=chunk_size,
    ):
        yield json.loads(encoded)


def iter_json_object_items(
    handle: TextIO,
    chunk_size: int = CHUNK_SIZE,
) -> Iterator[tuple[str, Any]]:
    """Yield key/value pairs from one top-level JSON object."""

    for encoded in _iter_collection_segments(
        handle,
        opening="{",
        closing="}",
        label="object",
        chunk_size=chunk_size,
    ):
        member = json.loads("{" + encoded + "}")
        if len(member) != 1:
            raise ValueError("invalid top-level JSON object member")
        yield next(iter(member.items()))


def iter_json_records(handle: TextIO, chunk_size: int = CHUNK_SIZE) -> Iterator[Any]:
    """Yield either a top-level array or one complete JSON value per line."""

    first_line = handle.readline()
    if not first_line:
        raise ValueError("empty JSON input")
    if first_line.lstrip().startswith("["):
        handle.seek(0)
        yield from iter_json_array(handle, chunk_size)
        return
    for line_number, line in enumerate(chain((first_line,), handle), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL record at line {line_number}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _doi(row: Mapping[str, Any]) -> str:
    message = row.get("message")
    if not isinstance(message, Mapping):
        message = row
    return _text(row.get("doi") or message.get("DOI")).casefold()


def audit_author_export(
    path: Path,
) -> tuple[dict[str, Any], Counter[str], Counter[str]]:
    selected_fields = (
        "firstname",
        "lastname",
        "orcid",
        "doi",
        "article_id",
        "year",
        "affiliation",
        "position",
        "author_position",
        "paper_authors",
        "title",
        "abstract",
        "venue",
        "journal",
    )
    presence: Counter[str] = Counter()
    doi_rows: Counter[str] = Counter()
    article_id_rows: Counter[str] = Counter()
    total = 0
    mappings = 0
    structured = 0
    forbidden_present = 0
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for item in iter_json_records(handle):
            total += 1
            if not isinstance(item, Mapping):
                continue
            mappings += 1
            for field in selected_fields:
                presence[field] += int(item.get(field) not in (None, "", [], {}))
            structured += int(bool(_text(item.get("firstname"))) and bool(_text(item.get("lastname"))))
            forbidden_present += int("original_name" in item)
            doi = _doi(item)
            if doi:
                doi_rows[doi] += 1
            article_id = _text(item.get("article_id")).casefold()
            if article_id:
                article_id_rows[article_id] += 1
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "items": total,
        "mapping_items": mappings,
        "structured_first_last": structured,
        "distinct_dois": len(doi_rows),
        "forbidden_original_name_present": forbidden_present,
        "selected_field_nonempty": dict(sorted(presence.items())),
    }, doi_rows, article_id_rows


def audit_article_author_map(path: Path) -> tuple[dict[str, Any], set[str]]:
    article_ids: set[str] = set()
    articles = 0
    list_values = 0
    author_rows = 0
    structured_rows = 0
    orcid_rows = 0
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_article_id, authors in iter_json_object_items(handle):
            articles += 1
            article_id = _text(raw_article_id).casefold()
            if article_id:
                article_ids.add(article_id)
            if not isinstance(authors, list):
                continue
            list_values += 1
            for author in authors:
                if not isinstance(author, Mapping):
                    continue
                author_rows += 1
                structured_rows += int(
                    bool(_text(author.get("given")))
                    and bool(_text(author.get("family")))
                )
                orcid_rows += int(bool(_text(author.get("orcid") or author.get("ORCID"))))
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "articles": articles,
        "distinct_article_ids": len(article_ids),
        "articles_with_author_list": list_values,
        "author_rows": author_rows,
        "author_rows_with_structured_given_family": structured_rows,
        "author_rows_with_orcid": orcid_rows,
        "source_position_available_from_list_order": author_rows,
        "record_values_emitted": False,
    }, article_ids


def audit_work_export(path: Path) -> tuple[dict[str, Any], set[str]]:
    work_presence: Counter[str] = Counter()
    author_presence: Counter[str] = Counter()
    dois: set[str] = set()
    items = 0
    mappings = 0
    author_rows = 0
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for item in iter_json_records(handle):
            items += 1
            if not isinstance(item, Mapping):
                continue
            mappings += 1
            message = item.get("message")
            if not isinstance(message, Mapping):
                message = item
            doi = _doi(item)
            if doi:
                dois.add(doi)
            for field in ("title", "abstract", "container-title", "published", "author"):
                work_presence[field] += int(message.get(field) not in (None, "", [], {}))
            authors = message.get("author") or []
            if not isinstance(authors, list):
                continue
            for position, author in enumerate(authors):
                if not isinstance(author, Mapping):
                    continue
                author_rows += 1
                author_presence["implicit_source_position"] += int(position >= 0)
                for field in ("given", "family", "ORCID", "affiliation"):
                    author_presence[field] += int(author.get(field) not in (None, "", [], {}))
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "items": items,
        "mapping_items": mappings,
        "distinct_dois": len(dois),
        "work_field_nonempty": dict(sorted(work_presence.items())),
        "raw_author_rows": author_rows,
        "raw_author_field_nonempty": dict(sorted(author_presence.items())),
    }, dois


def build_report(
    author_path: Path,
    work_path: Path | None = None,
    article_authors_path: Path | None = None,
) -> dict[str, Any]:
    author_report, author_doi_rows, article_id_rows = audit_author_export(author_path)
    article_author_report: dict[str, Any] = {
        "provided": False,
        "complete_paper_author_lists_available": False,
    }
    article_id_join: dict[str, Any] = {
        "available": False,
        "author_rows_total_with_article_id": sum(article_id_rows.values()),
    }
    if article_authors_path is not None:
        article_author_report, mapped_article_ids = audit_article_author_map(
            article_authors_path
        )
        joined_article_ids = set(article_id_rows).intersection(mapped_article_ids)
        article_author_report["provided"] = True
        article_author_report["complete_paper_author_lists_available"] = True
        article_id_join = {
            "available": True,
            "distinct_joined_article_ids": len(joined_article_ids),
            "author_rows_on_joined_article_ids": sum(
                article_id_rows[article_id] for article_id in joined_article_ids
            ),
            "author_rows_total_with_article_id": sum(article_id_rows.values()),
        }
    if work_path is None:
        return {
            "schema_version": "project2_s2and_coverage_audit_v1",
            "contains_record_values": False,
            "author_export": author_report,
            "article_author_map": article_author_report,
            "article_id_join": article_id_join,
            "work_export": {
                "provided": False,
                "paper_context_available": False,
            },
            "doi_join": {
                "available": False,
                "author_rows_total_with_doi": sum(author_doi_rows.values()),
            },
        }
    work_report, work_dois = audit_work_export(work_path)
    joined_dois = set(author_doi_rows).intersection(work_dois)
    return {
        "schema_version": "project2_s2and_coverage_audit_v1",
        "contains_record_values": False,
        "author_export": author_report,
        "article_author_map": article_author_report,
        "article_id_join": article_id_join,
        "work_export": work_report,
        "doi_join": {
            "available": True,
            "distinct_joined_dois": len(joined_dois),
            "author_rows_on_joined_dois": sum(author_doi_rows[doi] for doi in joined_dois),
            "author_rows_total_with_doi": sum(author_doi_rows.values()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--works", type=Path)
    parser.add_argument("--article-authors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args.authors, args.works, args.article_authors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    join = report["doi_join"]
    print(
        "coverage_audit_complete "
        f"authors={report['author_export']['items']} "
        f"article_map={report['article_author_map'].get('articles', 'unavailable')} "
        f"works={report['work_export'].get('items', 'unavailable')} "
        f"joined_dois={join.get('distinct_joined_dois', 'unavailable')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
