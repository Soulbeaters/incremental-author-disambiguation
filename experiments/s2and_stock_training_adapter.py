"""Build a leakage-audited stock-S2AND training dataset.

The public Crossref--ORCID identity is supervision, not a model feature.  This
adapter turns the already-whitelisted replay mentions into the official S2AND
``signatures``/``papers``/``specter_embeddings``/``clusters`` structures and
records an exact temporal split:

* years through ``train_through_year``: pairwise training;
* ``validation_year``: model and clustering hyperparameter selection;
* ``test_year``: frozen development test.

No source identity string is returned.  Cluster identifiers are salted hashes,
and the feature payload contains neither ORCID nor ``original_name``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from experiments.s2and_official_adapter import build_s2and_service_payload
from experiments.s2and_public_replay import ReplayMention


@dataclass(frozen=True)
class StockS2ANDTrainingData:
    payload: dict[str, Any]
    clusters: dict[str, dict[str, list[str]]]
    train_signature_ids: tuple[str, ...]
    validation_signature_ids: tuple[str, ...]
    test_signature_ids: tuple[str, ...]
    audit: dict[str, Any]


def _hash_token(namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}\0{value}".encode("utf-8")).hexdigest()
    return f"{namespace}:{digest[:24]}"


def _role(
    year: int,
    *,
    train_through_year: int,
    validation_year: int,
    test_year: int,
) -> str | None:
    if year <= train_through_year:
        return "train"
    if year == validation_year:
        return "validation"
    if year == test_year:
        return "test"
    return None


def exact_time_split_ratios(
    train_size: int,
    validation_size: int,
    test_size: int,
) -> tuple[float, float, float]:
    """Return ratios that reproduce exact integer boundaries in ``ANDData``.

    Official S2AND computes ``int(total * ratio)`` independently for train and
    validation.  A quarter-record interior offset avoids floating-point
    truncation at the exact boundary while leaving all three partitions
    non-empty.
    """

    sizes = (int(train_size), int(validation_size), int(test_size))
    if any(size <= 0 for size in sizes):
        raise ValueError("stock S2AND temporal train/validation/test roles must be non-empty")
    total = sum(sizes)
    train_ratio = (sizes[0] + 0.25) / total
    validation_ratio = (sizes[1] + 0.25) / total
    test_ratio = 1.0 - train_ratio - validation_ratio
    if (
        int(total * train_ratio) != sizes[0]
        or int(total * validation_ratio) != sizes[1]
        or test_ratio <= 0
        or train_ratio + validation_ratio + test_ratio != 1.0
    ):
        raise AssertionError("failed to encode exact official S2AND temporal boundaries")
    return train_ratio, validation_ratio, test_ratio


def _pair_audit(
    rows: Sequence[tuple[str, ReplayMention]],
) -> dict[str, dict[str, int]]:
    block_sizes: Counter[tuple[str, str]] = Counter()
    identity_sizes: Counter[tuple[str, str, str]] = Counter()
    for role, mention in rows:
        block_sizes[(role, mention.block)] += 1
        identity_sizes[(role, mention.block, mention.identity)] += 1

    result: dict[str, dict[str, int]] = {}
    for role in ("train", "validation", "test"):
        possible = sum(
            size * (size - 1) // 2
            for (observed_role, _block), size in block_sizes.items()
            if observed_role == role
        )
        positive = sum(
            size * (size - 1) // 2
            for (observed_role, _block, _identity), size in identity_sizes.items()
            if observed_role == role
        )
        result[role] = {
            "within_block_possible_pairs": possible,
            "within_block_positive_pairs": positive,
            "within_block_negative_pairs": possible - positive,
        }
    return result


def _assert_feature_boundary(payload: Mapping[str, Any]) -> None:
    forbidden_keys = {
        "original_name",
        "orcid",
        "gold_author_id",
        "identity",
        "author_id",
        "source_ids",
        "source_id_source",
    }

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if str(key).casefold() in forbidden_keys:
                    raise AssertionError(
                        f"forbidden identity field in stock-S2AND features: {key}"
                    )
                visit(nested)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for nested in value:
                visit(nested)

    visit(payload)
    for signature in payload["signatures"].values():
        if signature.get("sourced_author_ids"):
            raise AssertionError("sourced author identity leaked into stock-S2AND features")
        if signature.get("sourced_author_source") is not None:
            raise AssertionError("sourced author provenance leaked into stock-S2AND features")


def build_stock_s2and_training_data(
    mentions: Sequence[ReplayMention],
    *,
    train_through_year: int = 2022,
    validation_year: int = 2023,
    test_year: int = 2024,
) -> StockS2ANDTrainingData:
    """Create stock-S2AND training inputs with identity outside the features."""

    if not (train_through_year < validation_year < test_year):
        raise ValueError("expected train_through_year < validation_year < test_year")

    selected: list[tuple[str, ReplayMention]] = []
    paper_roles: dict[str, str] = {}
    seen_mentions: set[tuple[str, int, str]] = set()
    for mention in mentions:
        role = _role(
            int(mention.year),
            train_through_year=train_through_year,
            validation_year=validation_year,
            test_year=test_year,
        )
        if role is None:
            continue
        mention_key = (mention.doi, int(mention.author_position), mention.identity)
        if mention_key in seen_mentions:
            raise ValueError("duplicate labelled mention at stock-S2AND boundary")
        seen_mentions.add(mention_key)
        previous_role = paper_roles.setdefault(mention.doi, role)
        if previous_role != role:
            raise ValueError("temporal paper leakage at stock-S2AND boundary")
        selected.append((role, mention))

    role_order = {"train": 0, "validation": 1, "test": 2}
    selected.sort(
        key=lambda item: (
            role_order[item[0]],
            int(item[1].year),
            item[1].doi,
            int(item[1].author_position),
            hashlib.sha256(item[1].identity.encode("utf-8")).digest(),
        )
    )
    if not selected:
        raise ValueError("stock-S2AND adapter received no mentions in the requested years")

    ordered_mentions = [mention for _role_name, mention in selected]
    rows = [
        mention.adapter_row(include_history_label=True)
        for mention in ordered_mentions
    ]
    embeddings = {
        mention.doi: mention.paper.embedding
        for mention in ordered_mentions
    }
    service_payload = build_s2and_service_payload(
        rows,
        [],
        paper_embeddings=embeddings,
    )

    signature_ids = service_payload.history_signature_ids
    if len(signature_ids) != len(selected):
        raise AssertionError("stock-S2AND signature cardinality mismatch")

    cluster_members: dict[str, list[str]] = defaultdict(list)
    role_signatures: dict[str, list[str]] = defaultdict(list)
    role_identities: dict[str, set[str]] = defaultdict(set)
    role_blocks: dict[str, set[str]] = defaultdict(set)
    for signature_id, (role, mention) in zip(signature_ids, selected, strict=True):
        cluster_members[_hash_token("cluster", mention.identity)].append(signature_id)
        role_signatures[role].append(signature_id)
        role_identities[role].add(mention.identity)
        role_blocks[role].add(mention.block)

    clusters = {
        cluster_id: {"signature_ids": sorted(member_ids)}
        for cluster_id, member_ids in sorted(cluster_members.items())
    }
    feature_payload = {
        "signatures": service_payload.payload["signatures"],
        "papers": service_payload.payload["papers"],
        "paper_embeddings": service_payload.payload["paper_embeddings"],
    }
    _assert_feature_boundary(feature_payload)

    counts = {role: len(role_signatures[role]) for role in role_order}
    exact_time_split_ratios(
        counts["train"],
        counts["validation"],
        counts["test"],
    )
    audit = {
        "schema_version": "project2_stock_s2and_training_audit_v1",
        "contains_record_values": False,
        "label_use": "hashed cluster membership only",
        "feature_boundary": {
            "original_name_used": False,
            "orcid_used_as_feature": False,
            "query_or_future_identity_used_as_feature": False,
        },
        "years": {
            "train_through": int(train_through_year),
            "validation": int(validation_year),
            "test": int(test_year),
        },
        "signatures": counts,
        "papers": {
            role: sum(observed_role == role for observed_role in paper_roles.values())
            for role in role_order
        },
        "blocks": {role: len(role_blocks[role]) for role in role_order},
        "identities": {role: len(role_identities[role]) for role in role_order},
        "identity_overlap": {
            "train_validation": len(role_identities["train"] & role_identities["validation"]),
            "train_test": len(role_identities["train"] & role_identities["test"]),
            "validation_test": len(
                role_identities["validation"] & role_identities["test"]
            ),
        },
        "pair_opportunities": _pair_audit(selected),
        "clusters": len(clusters),
    }
    return StockS2ANDTrainingData(
        payload=feature_payload,
        clusters=clusters,
        train_signature_ids=tuple(role_signatures["train"]),
        validation_signature_ids=tuple(role_signatures["validation"]),
        test_signature_ids=tuple(role_signatures["test"]),
        audit=audit,
    )


def verify_official_time_split(
    dataset: Any,
    expected: StockS2ANDTrainingData,
) -> dict[str, int]:
    """Fail closed unless official ``ANDData`` reproduces the registered split."""

    train_blocks, validation_blocks, test_blocks = dataset.split_cluster_signatures()

    def flatten(blocks: Mapping[str, Sequence[str]]) -> set[str]:
        return {
            str(signature_id)
            for signature_ids in blocks.values()
            for signature_id in signature_ids
        }

    observed = (
        flatten(train_blocks),
        flatten(validation_blocks),
        flatten(test_blocks),
    )
    registered = (
        set(expected.train_signature_ids),
        set(expected.validation_signature_ids),
        set(expected.test_signature_ids),
    )
    if observed != registered:
        raise ValueError("official ANDData did not reproduce the registered temporal split")
    if observed[0] & observed[1] or observed[0] & observed[2] or observed[1] & observed[2]:
        raise ValueError("official ANDData temporal split overlaps")
    return {
        "train": len(observed[0]),
        "validation": len(observed[1]),
        "test": len(observed[2]),
    }
