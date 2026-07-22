"""Stream an aggregate-only S2AND field-coverage audit over Crossref JSON.

The source files are large top-level JSON arrays.  This module uses only the
standard library, never prints record values, and retains only counters plus
normalized DOI keys needed for aggregate join coverage.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Iterator, Mapping, TextIO


CHUNK_SIZE = 64 * 1024


def iter_json_array(handle: TextIO, chunk_size: int = CHUNK_SIZE) -> Iterator[Any]:
    """Yield items from one top-level JSON array without loading it in memory."""

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
            if chunk[index] != "[":
                raise ValueError("expected a top-level JSON array")
            started = True
            index += 1

        segment_start = index
        while index < len(chunk):
            character = chunk[index]
            if finished:
                if not character.isspace():
                    raise ValueError("unexpected content after top-level JSON array")
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
                if character == "]" and nested_depth == 0:
                    item_parts.append(chunk[segment_start:index])
                    item_text = "".join(item_parts).strip()
                    if item_text:
                        yield json.loads(item_text)
                    item_parts.clear()
                    finished = True
                    segment_start = index + 1
                elif nested_depth <= 0:
                    raise ValueError("unbalanced JSON array item")
                else:
                    nested_depth -= 1
            elif character == "," and nested_depth == 0:
                item_parts.append(chunk[segment_start:index])
                item_text = "".join(item_parts).strip()
                if not item_text:
                    raise ValueError("empty JSON array item")
                yield json.loads(item_text)
                item_parts.clear()
                segment_start = index + 1
            index += 1
        if not finished and segment_start < len(chunk):
            item_parts.append(chunk[segment_start:])

    if not started:
        raise ValueError("empty JSON input; expected a top-level array")
    if not finished:
        raise ValueError("unterminated top-level JSON array")


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


def audit_author_export(path: Path) -> tuple[dict[str, Any], Counter[str]]:
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
    total = 0
    mappings = 0
    structured = 0
    forbidden_present = 0
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for item in iter_json_array(handle):
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
    }, doi_rows


def audit_work_export(path: Path) -> tuple[dict[str, Any], set[str]]:
    work_presence: Counter[str] = Counter()
    author_presence: Counter[str] = Counter()
    dois: set[str] = set()
    items = 0
    mappings = 0
    author_rows = 0
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for item in iter_json_array(handle):
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


def build_report(author_path: Path, work_path: Path) -> dict[str, Any]:
    author_report, author_doi_rows = audit_author_export(author_path)
    work_report, work_dois = audit_work_export(work_path)
    joined_dois = set(author_doi_rows).intersection(work_dois)
    return {
        "schema_version": "project2_s2and_coverage_audit_v1",
        "contains_record_values": False,
        "author_export": author_report,
        "work_export": work_report,
        "doi_join": {
            "distinct_joined_dois": len(joined_dois),
            "author_rows_on_joined_dois": sum(author_doi_rows[doi] for doi in joined_dois),
            "author_rows_total_with_doi": sum(author_doi_rows.values()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--works", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args.authors, args.works)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    join = report["doi_join"]
    print(
        "coverage_audit_complete "
        f"authors={report['author_export']['items']} "
        f"works={report['work_export']['items']} "
        f"joined_dois={join['distinct_joined_dois']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
