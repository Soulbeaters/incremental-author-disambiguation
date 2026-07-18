"""Replay the ISTINA runtime on the official AMiner KDD'18 benchmark.

The archive is not redistributed. Download ``na-data-kdd18.zip`` from the
official AMiner URL, extract it, and point ``--data-root`` at ``data/global``.
Every labelled mention is validated against the paper author position and
entity identifier before it can enter the replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.istina_runtime_replay import evaluate  # noqa: E402
from integrations.istina_pipeline import (  # noqa: E402
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
)


AMINER_KDD18_URL = "https://static.aminer.cn/misc/na-data-kdd18.zip"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tagged_publication_parts(tagged_id: str) -> Tuple[str, int]:
    try:
        publication_id, raw_position = str(tagged_id).rsplit("-", 1)
        position = int(raw_position)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid AMiner tagged publication ID: {tagged_id!r}") from exc
    if not publication_id or position < 0:
        raise ValueError(f"invalid AMiner tagged publication ID: {tagged_id!r}")
    return publication_id, position


def _structured_block_name(block_name: str) -> Tuple[str, str]:
    parts = [part for part in str(block_name).replace("_", " ").split() if part]
    if not parts:
        return "", ""
    return parts[-1], " ".join(parts[:-1])


def load_aminer_mentions(
    data_root: Path,
    label_split: str = "test_100",
    start_name: int = 0,
    max_names: int | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    labels_path = data_root / f"name_to_pubs_{label_split}.json"
    publications_path = data_root / "pubs_raw.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    publications = json.loads(publications_path.read_text(encoding="utf-8"))
    names = sorted(labels)
    end = start_name + max_names if max_names is not None else None
    selected_names = names[start_name:end]
    integrity: Counter[str] = Counter()
    mentions: List[Dict[str, Any]] = []

    for block_name in selected_names:
        lastname, firstname = _structured_block_name(block_name)
        for author_id, tagged_ids in labels[block_name].items():
            for tagged_id in tagged_ids:
                publication_id, position = tagged_publication_parts(tagged_id)
                publication = publications.get(publication_id)
                if publication is None:
                    raise ValueError(
                        f"AMiner label {tagged_id!r} references a missing publication"
                    )
                authors = list(publication.get("authors") or [])
                if position >= len(authors):
                    raise ValueError(
                        f"AMiner label {tagged_id!r} has an out-of-range author position"
                    )
                target = authors[position]
                if str(target.get("id") or "") != str(author_id):
                    raise ValueError(
                        f"AMiner label {tagged_id!r} does not match author {author_id!r}"
                    )
                integrity["validated_mentions"] += 1
                mentions.append({
                    "mention_id": str(tagged_id),
                    "article_id": publication_id,
                    "position": position,
                    "gold_author_id": str(author_id),
                    "name": str(
                        target.get("name") or str(block_name).replace("_", " ")
                    ),
                    "lastname": lastname,
                    "firstname": firstname,
                    "orcid": "",
                    "coauthors": [
                        str(author.get("name") or "")
                        for index, author in enumerate(authors)
                        if index != position and author.get("name")
                    ],
                    "journal": str(publication.get("venue") or ""),
                    "affiliation": str(target.get("org") or ""),
                    "year": int(publication.get("year") or 0),
                    "block_name": str(block_name),
                    "source": "aminer_kdd18",
                })

    mentions.sort(key=lambda row: (
        row["year"],
        row["article_id"],
        row["position"],
        row["gold_author_id"],
    ))
    for article_index, mention in enumerate(mentions, start=1):
        mention["article_index"] = article_index
    return mentions, {
        "available_names": len(names),
        "selected_names": len(selected_names),
        "start_name": start_name,
        "integrity": dict(integrity),
        "labels_file": labels_path.name,
        "publications_file": publications_path.name,
    }


def _mentions_by_author(
    mentions: Iterable[Mapping[str, Any]],
) -> Dict[str, List[Mapping[str, Any]]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for mention in mentions:
        grouped[str(mention["gold_author_id"])].append(mention)
    return grouped


def split_complete_papers(
    mentions: List[Dict[str, Any]],
    history_policy: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped = _mentions_by_author(mentions)
    if history_policy == "first-history":
        history_article_ids = {
            str(group[0]["article_id"])
            for group in grouped.values()
            if len(group) >= 2
        }
        history = [
            mention for mention in mentions
            if str(mention["article_id"]) in history_article_ids
        ]
        test = [
            mention for mention in mentions
            if str(mention["article_id"]) not in history_article_ids
        ]
    elif history_policy == "last-test":
        test_article_ids = {
            str(group[-1]["article_id"])
            for group in grouped.values()
        }
        history = [
            mention for mention in mentions
            if str(mention["article_id"]) not in test_article_ids
        ]
        test = [
            mention for mention in mentions
            if str(mention["article_id"]) in test_article_ids
        ]
    else:
        raise ValueError(f"unsupported AMiner history policy: {history_policy}")
    overlap = (
        {str(mention["article_id"]) for mention in history}
        & {str(mention["article_id"]) for mention in test}
    )
    if overlap:
        raise AssertionError("AMiner history/test split contains publication leakage")
    return history, test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--label-split",
        choices=("train_500", "test_100"),
        default="test_100",
    )
    parser.add_argument("--start-name", type=int, default=0)
    parser.add_argument("--max-names", type=int)
    parser.add_argument(
        "--history-policy",
        choices=("first-history", "last-test"),
        default="last-test",
    )
    parser.add_argument("--topk", type=int, default=20)
    parser.add_argument(
        "--enable-calibrated-candidate-rescue",
        action="store_true",
        help="Enable the OpenAlex-calibrated model for explicit cross-domain ablation.",
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    mentions, integrity = load_aminer_mentions(
        args.data_root,
        label_split=args.label_split,
        start_name=args.start_name,
        max_names=args.max_names,
    )
    history, test = split_complete_papers(mentions, args.history_policy)
    pipeline = IstinaDisambiguationPipeline.from_history_mentions(
        history,
        config=IstinaPipelineConfig(
            mode="fs",
            accept_threshold=-0.5,
            reject_threshold=-4.0,
            min_accept_margin=1e-9,
            require_context_for_low_name_accept=True,
            use_remote_fallback=False,
            topk=args.topk,
            enable_calibrated_candidate_rescue=(
                args.enable_calibrated_candidate_rescue
            ),
        ),
    )
    result = {
        "protocol": {
            "source": "AMiner KDD'18 official author-disambiguation benchmark",
            "source_url": AMINER_KDD18_URL,
            "archive_sha256": (
                file_sha256(args.archive) if args.archive else None
            ),
            "label_split": args.label_split,
            "history_policy": args.history_policy,
            "history_mentions": len(history),
            "test_mentions": len(test),
            "article_overlap": 0,
            "topk": args.topk,
            "calibrated_candidate_rescue": (
                args.enable_calibrated_candidate_rescue
            ),
            **integrity,
        },
        **evaluate(pipeline, test, service_records={}),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(
        {
            key: value
            for key, value in result.items()
            if key not in {"records", "error_samples"}
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
