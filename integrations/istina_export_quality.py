"""Deterministic, lossless quality controls for ISTINA publication exports."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple


def deduplicate_exact_author_rows(
    articles: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Remove byte-equivalent author rows within a paper, preserving order.

    This deliberately does not collapse merely similar names or repeated author
    identifiers.  Those cases require adjudication because they can represent
    legitimate ambiguity or corrupt labels.
    """

    cleaned: List[Dict[str, Any]] = []
    removed = 0
    for article in articles:
        article_copy = dict(article)
        authors = []
        seen = set()
        for author in article.get("authors") or []:
            author_copy = dict(author)
            key = json.dumps(
                author_copy,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            authors.append(author_copy)
        article_copy["authors"] = authors
        cleaned.append(article_copy)
    return cleaned, removed


__all__ = ["deduplicate_exact_author_rows"]
