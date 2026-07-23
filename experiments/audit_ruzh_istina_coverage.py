"""Aggregate-only RuZh coverage audit for a structured ISTINA export."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from disambiguation_engine.multilingual_name_features import script_inventory  # noqa: E402
from disambiguation_engine.ruzh_name_evidence import name_evidence  # noqa: E402


ALLOWED_AUTHOR_FIELDS = (
    "author_id",
    "id",
    "firstname",
    "first_name",
    "middlename",
    "middle_name",
    "lastname",
    "last_name",
    "position",
    "affiliation",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def field(record: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(record.get(name) or "").strip()
        if value:
            return value
    return ""


def clean_author(author: Mapping[str, Any]) -> dict[str, Any]:
    """Whitelist real structured fields without ever reading original_name."""

    return {
        key: author.get(key)
        for key in ALLOWED_AUTHOR_FIELDS
        if key in author
    }


def author_identity(author: Mapping[str, Any]) -> str:
    value = author.get("author_id")
    if value in (None, ""):
        value = author.get("id")
    return "" if value in (None, "") else str(value)


def structured_parts(author: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        field(author, "firstname", "first_name"),
        field(author, "middlename", "middle_name"),
        field(author, "lastname", "last_name"),
    )


def load_mentions(path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, list):
        raise ValueError("expected a list of ISTINA articles")
    mentions: list[dict[str, Any]] = []
    raw_authors = 0
    duplicates_removed = 0
    for article_index, article in enumerate(document, start=1):
        paper_id = str(
            article.get("id")
            or article.get("article_id")
            or article.get("doi")
            or article_index
        )
        seen: set[str] = set()
        for fallback_position, source in enumerate(
            article.get("authors") or (), start=1
        ):
            raw_authors += 1
            author = clean_author(source)
            duplicate_key = json.dumps(
                author,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if duplicate_key in seen:
                duplicates_removed += 1
                continue
            seen.add(duplicate_key)
            first, middle, last = structured_parts(author)
            mentions.append({
                "paper_id": paper_id,
                "year": article.get("year"),
                "position": author.get("position") or fallback_position,
                "identity": author_identity(author),
                "first": first,
                "middle": middle,
                "last": last,
            })
    return mentions, {
        "articles": len(document),
        "raw_authorships": raw_authors,
        "exact_whitelisted_duplicates_removed": duplicates_removed,
        "effective_authorships": len(mentions),
    }


def split_counts(
    mentions: list[dict[str, Any]],
    *,
    cutoff_year: int,
) -> dict[str, int]:
    history_ids = {
        mention["identity"]
        for mention in mentions
        if mention["identity"]
        and isinstance(mention.get("year"), int)
        and mention["year"] <= cutoff_year
    }
    test = [
        mention
        for mention in mentions
        if mention["identity"]
        and isinstance(mention.get("year"), int)
        and mention["year"] > cutoff_year
        and mention["evidence"].target
    ]
    return {
        "target_test": len(test),
        "target_known": sum(
            mention["identity"] in history_ids for mention in test
        ),
        "target_new": sum(
            mention["identity"] not in history_ids for mention in test
        ),
    }


def audit(path: Path, cutoff_year: int) -> dict[str, Any]:
    mentions, input_counts = load_mentions(path)
    reasons: Counter[str] = Counter()
    scripts: Counter[str] = Counter()
    identities: Counter[str] = Counter()
    target_id_scripts: dict[str, set[str]] = defaultdict(set)
    target = []
    structured = []
    for mention in mentions:
        if not mention["first"] or not mention["last"]:
            continue
        structured.append(mention)
        evidence = name_evidence(
            mention["first"],
            mention["middle"],
            mention["last"],
        )
        mention["evidence"] = evidence
        full = " ".join(
            value
            for value in (
                mention["first"],
                mention["middle"],
                mention["last"],
            )
            if value
        )
        inventory = script_inventory(full)
        signature = "+".join(sorted(inventory)) or "none"
        scripts[signature] += 1
        if not evidence.target:
            continue
        target.append(mention)
        reasons.update(evidence.reasons)
        if mention["identity"]:
            identities[mention["identity"]] += 1
            target_id_scripts[mention["identity"]].add(signature)

    repeated_ids = {
        identity for identity, count in identities.items() if count >= 2
    }
    return {
        "schema_version": "project2_ruzh_istina_coverage_v1",
        "contains_record_values": False,
        "original_name_read": False,
        "input": {
            "sha256": sha256_file(path),
            **input_counts,
        },
        "coverage": {
            "structured_authorships": len(structured),
            "target_authorships": len(target),
            "target_share": (
                len(target) / len(structured) if structured else 0.0
            ),
            "target_reasons": dict(sorted(reasons.items())),
            "structured_script_signatures": dict(sorted(scripts.items())),
            "target_labeled_authorships": sum(
                bool(mention["identity"]) for mention in target
            ),
            "target_unique_labeled_identities": len(identities),
            "target_repeated_labeled_identities": len(repeated_ids),
            "target_mentions_from_repeated_identities": sum(
                identities[identity] for identity in repeated_ids
            ),
            "target_cross_script_labeled_identities": sum(
                len(values) >= 2 for values in target_id_scripts.values()
            ),
        },
        "temporal": {
            "history_through_year": cutoff_year,
            **split_counts(structured, cutoff_year=cutoff_year),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cutoff-year", type=int, default=2023)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.dataset, args.cutoff_year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "target_authorships": result["coverage"]["target_authorships"],
        "target_repeated_labeled_identities": result["coverage"][
            "target_repeated_labeled_identities"
        ],
        "temporal": result["temporal"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
