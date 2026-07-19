"""Audit ISTINA exports for production-gold and shadow-sample readiness.

The report is privacy-preserving: committed output contains aggregate counts,
checks, and input hashes only.  Potential label conflicts can optionally be
written to a separate, private adjudication queue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.istina_export_temporal_evaluation import (
    article_id,
    exported_author_name,
    iter_mentions,
    load_articles,
    mention_identity,
    split_mentions,
)
from experiments.istina_runtime_replay import load_service_records
from disambiguation_engine.structured_name_repair import structured_name_parts
from integrations.istina_export_quality import deduplicate_exact_author_rows


@dataclass(frozen=True)
class GoldReadinessCriteria:
    min_test_mentions: int = 10_000
    min_existing_mentions: int = 1_000
    min_new_mentions: int = 1_000
    min_shared_shadow_mentions: int = 500
    min_disciplines: int = 5
    min_distinct_years: int = 3
    min_gold_id_coverage: float = 0.95
    min_title_coverage: float = 0.95
    min_year_coverage: float = 0.95
    max_unresolved_label_issues: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name.startswith("min_") and value < 0:
                raise ValueError(f"{name} cannot be negative")
        for value in (
            self.min_gold_id_coverage,
            self.min_title_coverage,
            self.min_year_coverage,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("coverage criteria must be within [0, 1]")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script(value: str) -> str:
    counts = {
        "latin": sum("a" <= char <= "z" for char in value.casefold()),
        "cyrillic": sum("\u0400" <= char <= "\u04ff" for char in value.casefold()),
        "cjk": sum("\u4e00" <= char <= "\u9fff" for char in value),
    }
    script, count = max(counts.items(), key=lambda item: item[1])
    return script if count else "other"


def _discipline(article: Mapping[str, Any]) -> str:
    return str(
        article.get("discipline")
        or article.get("field")
        or article.get("faculty")
        or article.get("department")
        or article.get("domain")
        or ""
    ).strip()


def _issue_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def build_adjudication_issues(
    articles: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Return deterministic potential-gold issues with raw review context."""

    issues: List[Dict[str, Any]] = []
    seen_article_ids: Dict[str, int] = {}
    profiles_by_author: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for article_index, article in enumerate(articles, start=1):
        paper_id = article_id(dict(article), article_index)
        if paper_id in seen_article_ids:
            payload = {
                "type": "duplicate_article_id",
                "article_id": paper_id,
                "first_article_index": seen_article_ids[paper_id],
                "duplicate_article_index": article_index,
            }
            issues.append({"issue_id": _issue_id(payload), **payload})
        else:
            seen_article_ids[paper_id] = article_index

        authors_seen_on_paper: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for position, author in enumerate(article.get("authors") or [], start=1):
            author_id = str(author.get("author_id") or author.get("id") or "").strip()
            name = exported_author_name(dict(author))
            if author_id:
                authors_seen_on_paper[author_id].append(dict(author))
                family, _ = structured_name_parts({
                    "name": name,
                    "lastname": author.get("lastname") or author.get("last_name") or "",
                    "firstname": author.get("firstname") or author.get("first_name") or "",
                })
                profiles_by_author[author_id].append({
                    "article_id": paper_id,
                    "article_index": article_index,
                    "position": author.get("position") or position,
                    "name": name,
                    "family": family,
                })
        for author_id, rows in sorted(authors_seen_on_paper.items()):
            unique_rows = {
                json.dumps(row, ensure_ascii=False, sort_keys=True)
                for row in rows
            }
            if len(rows) > 1 and len(unique_rows) > 1:
                payload = {
                    "type": "duplicate_author_id_on_paper",
                    "article_id": paper_id,
                    "author_id": author_id,
                    "occurrences": len(rows),
                    "distinct_rows": len(unique_rows),
                }
                issues.append({"issue_id": _issue_id(payload), **payload})

    for author_id, profiles in sorted(profiles_by_author.items()):
        families = sorted({
            profile["family"] for profile in profiles if profile.get("family")
        })
        incompatible_pairs = []
        for left_index, left in enumerate(families):
            for right in families[left_index + 1:]:
                if _script(left) != _script(right):
                    continue
                ratio = SequenceMatcher(None, left, right).ratio()
                if ratio < 0.25:
                    incompatible_pairs.append({
                        "left_family": left,
                        "right_family": right,
                        "similarity": ratio,
                    })
        if incompatible_pairs:
            payload = {
                "type": "potential_conflicting_author_identity",
                "author_id": author_id,
                "families": families,
                "incompatible_pairs": incompatible_pairs,
                "profiles": profiles,
            }
            issues.append({"issue_id": _issue_id({
                "type": payload["type"],
                "author_id": author_id,
                "families": families,
            }), **payload})

    return sorted(issues, key=lambda issue: (issue["type"], issue["issue_id"]))


def _check(
    name: str,
    observed: Any,
    required: Any,
    passed: bool,
    category: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "observed": observed,
        "required": required,
        "passed": bool(passed),
    }


def _split_summary(
    history: Sequence[Mapping[str, Any]],
    test: Sequence[Mapping[str, Any]],
    service_records: Mapping[Tuple[str, str, str, str, str], Mapping[str, Any]],
) -> Dict[str, Any]:
    known_ids = {
        str(mention.get("gold_author_id"))
        for mention in history if mention.get("gold_author_id")
    }
    existing = sum(
        str(mention.get("gold_author_id") or "") in known_ids for mention in test
    )
    history_papers = {str(mention.get("article_id") or "") for mention in history}
    test_papers = {str(mention.get("article_id") or "") for mention in test}
    shadow = sum(
        mention_identity(dict(mention)) in service_records
        and str(mention.get("gold_author_id") or "") in known_ids
        for mention in test
    )
    return {
        "history_mentions": len(history),
        "test_mentions": len(test),
        "existing_mentions": existing,
        "new_mentions": len(test) - existing,
        "known_author_ids": len(known_ids),
        "history_papers": len(history_papers),
        "test_papers": len(test_papers),
        "paper_overlap": len(history_papers & test_papers),
        "shared_shadow_mentions": shadow,
    }


def assess_gold_readiness(
    articles: Sequence[Mapping[str, Any]],
    service_records: Optional[
        Mapping[Tuple[str, str, str, str, str], Mapping[str, Any]]
    ] = None,
    decisions: Optional[Mapping[str, str]] = None,
    criteria: Optional[GoldReadinessCriteria] = None,
    train_through_year: int = 2023,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    criteria = criteria or GoldReadinessCriteria()
    service_records = service_records or {}
    decisions = {str(key): str(value) for key, value in (decisions or {}).items()}
    cleaned_articles, exact_duplicates_removed = deduplicate_exact_author_rows(
        articles
    )
    mentions = list(iter_mentions(cleaned_articles))
    with_gold = [mention for mention in mentions if mention.get("gold_author_id")]
    issues = build_adjudication_issues(cleaned_articles)
    unresolved = [
        issue for issue in issues
        if decisions.get(issue["issue_id"]) not in {
            "confirmed_same",
            "corrected",
            "not_an_issue",
        }
    ]

    temporal_history, temporal_test = split_mentions(
        with_gold,
        "temporal",
        train_through_year,
    )
    holdout_history, holdout_test = split_mentions(
        with_gold,
        "per-author-holdout",
        train_through_year,
    )
    temporal = _split_summary(temporal_history, temporal_test, service_records)
    holdout = _split_summary(holdout_history, holdout_test, service_records)

    disciplines = Counter(
        discipline
        for discipline in (_discipline(article) for article in cleaned_articles)
        if discipline
    )
    years = Counter(
        str(article.get("year"))
        for article in cleaned_articles if article.get("year")
    )
    author_rows = [
        author
        for article in cleaned_articles
        for author in article.get("authors") or []
    ]
    article_total = len(cleaned_articles)
    raw_mention_total = sum(
        len(article.get("authors") or []) for article in articles
    )
    mention_total = len(mentions)
    gold_coverage = len(with_gold) / mention_total if mention_total else 0.0
    title_coverage = (
        sum(
            bool(str(article.get("title") or "").strip())
            for article in cleaned_articles
        )
        / article_total if article_total else 0.0
    )
    year_coverage = (
        sum(article.get("year") is not None for article in cleaned_articles)
        / article_total if article_total else 0.0
    )
    context_coverage = {
        "title": title_coverage,
        "year": year_coverage,
        "doi": (
            sum(
                bool(str(article.get("doi") or "").strip())
                for article in cleaned_articles
            )
            / article_total if article_total else 0.0
        ),
        "journal": (
            sum(
                bool(str(
                    article.get("journal") or article.get("venue") or ""
                ).strip())
                for article in cleaned_articles
            )
            / article_total if article_total else 0.0
        ),
        "discipline": sum(disciplines.values()) / article_total if article_total else 0.0,
        "affiliation": (
            sum(bool(str(author.get("affiliation") or "").strip()) for author in author_rows)
            / len(author_rows) if author_rows else 0.0
        ),
        "orcid": (
            sum(bool(str(author.get("orcid") or "").strip()) for author in author_rows)
            / len(author_rows) if author_rows else 0.0
        ),
    }

    checks = [
        _check("test_mentions", temporal["test_mentions"], f">={criteria.min_test_mentions}", temporal["test_mentions"] >= criteria.min_test_mentions, "sample"),
        _check("existing_mentions", temporal["existing_mentions"], f">={criteria.min_existing_mentions}", temporal["existing_mentions"] >= criteria.min_existing_mentions, "sample"),
        _check("new_mentions", temporal["new_mentions"], f">={criteria.min_new_mentions}", temporal["new_mentions"] >= criteria.min_new_mentions, "sample"),
        _check("shared_shadow_mentions", temporal["shared_shadow_mentions"], f">={criteria.min_shared_shadow_mentions}", temporal["shared_shadow_mentions"] >= criteria.min_shared_shadow_mentions, "sample"),
        _check("disciplines", len(disciplines), f">={criteria.min_disciplines}", len(disciplines) >= criteria.min_disciplines, "coverage"),
        _check("distinct_years", len(years), f">={criteria.min_distinct_years}", len(years) >= criteria.min_distinct_years, "coverage"),
        _check("gold_id_coverage", gold_coverage, f">={criteria.min_gold_id_coverage}", gold_coverage >= criteria.min_gold_id_coverage, "quality"),
        _check("title_coverage", title_coverage, f">={criteria.min_title_coverage}", title_coverage >= criteria.min_title_coverage, "quality"),
        _check("year_coverage", year_coverage, f">={criteria.min_year_coverage}", year_coverage >= criteria.min_year_coverage, "quality"),
        _check("paper_overlap", temporal["paper_overlap"], "0", temporal["paper_overlap"] == 0, "leakage"),
        _check("unresolved_label_issues", len(unresolved), f"<={criteria.max_unresolved_label_issues}", len(unresolved) <= criteria.max_unresolved_label_issues, "adjudication"),
    ]
    failures = [check for check in checks if not check["passed"]]
    report = {
        "schema_version": 1,
        "data_ready": not failures,
        "criteria": asdict(criteria),
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "dataset": {
            "articles": article_total,
            "raw_mentions": raw_mention_total,
            "mentions": mention_total,
            "mentions_with_gold": len(with_gold),
            "unique_gold_author_ids": len({
                str(mention.get("gold_author_id")) for mention in with_gold
            }),
            "cleaned_canonical_sha256": sha256_json(cleaned_articles),
            "disciplines": dict(sorted(disciplines.items())),
            "years": dict(sorted(years.items())),
            "context_coverage": context_coverage,
            "automatic_cleaning": {
                "exact_duplicate_author_rows_removed": exact_duplicates_removed,
                "policy": (
                    "only byte-equivalent author objects within the same paper"
                ),
            },
        },
        "production_temporal_split": temporal,
        "diagnostic_per_author_holdout": holdout,
        "adjudication": {
            "issues": len(issues),
            "unresolved": len(unresolved),
            "issue_types": dict(sorted(Counter(issue["type"] for issue in issues).items())),
            "issue_ids": [issue["issue_id"] for issue in issues],
        },
        "checks": checks,
        "failures": failures,
    }
    return report, issues


def _load_decisions(path: Optional[Path]) -> Dict[str, str]:
    if not path:
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, Mapping) and isinstance(document.get("decisions"), Mapping):
        document = document["decisions"]
    if not isinstance(document, Mapping):
        raise ValueError("adjudication decisions must be a JSON object")
    return {str(key): str(value) for key, value in document.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, nargs="+", required=True)
    parser.add_argument("--service-result", type=Path)
    parser.add_argument("--adjudication-decisions", type=Path)
    parser.add_argument("--adjudication-output", type=Path)
    parser.add_argument("--cleaned-output", type=Path)
    parser.add_argument("--train-through-year", type=int, default=2023)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    articles: List[Dict[str, Any]] = []
    for dataset_path in args.dataset:
        articles.extend(load_articles(dataset_path))
    service_records = load_service_records(args.service_result)
    report, issues = assess_gold_readiness(
        articles,
        service_records=service_records,
        decisions=_load_decisions(args.adjudication_decisions),
        train_through_year=args.train_through_year,
    )
    report["inputs"] = {
        "datasets": [
            {
                "name": path.name,
                "sha256": sha256_file(path),
            }
            for path in args.dataset
        ],
        "service_result": ({
            "name": args.service_result.name,
            "sha256": sha256_file(args.service_result),
        } if args.service_result else None),
        "adjudication_decisions": ({
            "name": args.adjudication_decisions.name,
            "sha256": sha256_file(args.adjudication_decisions),
        } if args.adjudication_decisions else None),
    }
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.adjudication_output:
        args.adjudication_output.parent.mkdir(parents=True, exist_ok=True)
        with args.adjudication_output.open("w", encoding="utf-8") as handle:
            for issue in issues:
                handle.write(json.dumps(issue, ensure_ascii=False) + "\n")
    if args.cleaned_output:
        cleaned_articles, _removed = deduplicate_exact_author_rows(articles)
        args.cleaned_output.parent.mkdir(parents=True, exist_ok=True)
        args.cleaned_output.write_text(
            json.dumps(cleaned_articles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps({
        "output": str(args.output),
        "data_ready": report["data_ready"],
        "passed": report["summary"]["passed"],
        "total": report["summary"]["total"],
        "temporal_test_mentions": report["production_temporal_split"]["test_mentions"],
        "temporal_existing_mentions": report["production_temporal_split"]["existing_mentions"],
        "shared_shadow_mentions": report["production_temporal_split"]["shared_shadow_mentions"],
        "unresolved_issues": report["adjudication"]["unresolved"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = [
    "GoldReadinessCriteria",
    "assess_gold_readiness",
    "build_adjudication_issues",
    "deduplicate_exact_author_rows",
]
