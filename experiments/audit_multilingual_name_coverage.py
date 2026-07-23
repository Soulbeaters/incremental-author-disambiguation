"""Aggregate-only audit for multilingual structured-name development coverage."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from disambiguation_engine.multilingual_name_features import (
    FEATURE_NAMES,
    StructuredName,
    multilingual_name_features,
    script_inventory,
)
from disambiguation_engine.surname_risk import (
    HIGH_RISK_EAST_ASIAN_ROMANIZED_SURNAMES,
)


SCHEMA_VERSION = "project2_multilingual_name_coverage_v1"
MAX_NAMES_PER_IDENTITY = 32


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _script_key(value: str) -> str:
    scripts = script_inventory(value)
    return "+".join(sorted(scripts)) if scripts else "missing"


def _structured_row(row: Mapping[str, Any]) -> dict[str, str]:
    """Whitelist observed structured fields; never copy unstructured aliases."""

    return {
        "firstname": str(
            row.get("firstname") or row.get("first_name") or ""
        ).strip(),
        "middlename": str(
            row.get("middlename") or row.get("middle_name") or ""
        ).strip(),
        "lastname": str(
            row.get("lastname")
            or row.get("last_name")
            or row.get("surname")
            or ""
        ).strip(),
    }


def _identity_label(row: Mapping[str, Any]) -> str:
    return str(row.get("orcid") or "").strip()


def audit(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    script_counts: Counter[str] = Counter()
    surname_counts: Counter[str] = Counter()
    identity_scripts: dict[str, set[frozenset[str]]] = defaultdict(set)
    identity_names: dict[str, set[StructuredName]] = defaultdict(set)
    truncated_identity_names = 0
    usable = 0

    for row in rows:
        structured = _structured_row(row)
        try:
            name = StructuredName.from_mapping(structured)
        except ValueError:
            continue
        usable += 1
        script = _script_key(name.full)
        script_counts[script] += 1
        surname_key = "".join(
            character
            for character in name.last.casefold()
            if character.isalpha()
        )
        surname_counts["short"] += int(len(surname_key) <= 2)
        surname_counts["east_asian_romanized"] += int(
            surname_key in HIGH_RISK_EAST_ASIAN_ROMANIZED_SURNAMES
        )
        label = _identity_label(row)
        if not label:
            continue
        identity_scripts[label].add(script_inventory(name.full))
        names = identity_names[label]
        if len(names) < MAX_NAMES_PER_IDENTITY:
            names.add(name)
        elif name not in names:
            truncated_identity_names += 1

    mixed_identity_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    feature_index = {
        name: index for index, name in enumerate(FEATURE_NAMES)
    }
    for identity, signatures in identity_scripts.items():
        if len(signatures) < 2:
            continue
        mixed_identity_counts["total"] += 1
        union = frozenset(
            script
            for signature in signatures
            for script in signature
        )
        mixed_identity_counts[
            "+".join(sorted(union)) or "missing"
        ] += 1
        names = sorted(
            identity_names[identity],
            key=lambda item: (item.last, item.first, item.middle),
        )
        for left_index, left in enumerate(names):
            left_scripts = script_inventory(left.full)
            for right in names[left_index + 1:]:
                right_scripts = script_inventory(right.full)
                if left_scripts.intersection(right_scripts):
                    continue
                pair_counts["cross_script_same_identity"] += 1
                features = multilingual_name_features(left, right)
                native = (
                    features[feature_index["family_native_similarity"]]
                    + features[feature_index["given_native_similarity"]]
                ) / 2.0
                latin = (
                    features[feature_index["family_latin_similarity"]]
                    + features[feature_index["given_latin_similarity"]]
                ) / 2.0
                palladius = (
                    features[feature_index["family_palladius_similarity"]]
                    + features[feature_index["given_palladius_similarity"]]
                ) / 2.0
                pair_counts["generic_latin_rescue_at_0_95"] += int(
                    native < 0.95 and latin >= 0.95
                )
                pair_counts["palladius_rescue_at_0_95"] += int(
                    native < 0.95 and palladius >= 0.95
                )

    return {
        "rows": len(rows),
        "usable_structured_rows": usable,
        "script_counts": dict(sorted(script_counts.items())),
        "surname_risk_counts": dict(sorted(surname_counts.items())),
        "labelled_identities": len(identity_scripts),
        "mixed_script_identities": dict(
            sorted(mixed_identity_counts.items())
        ),
        "same_identity_pair_opportunities": dict(sorted(pair_counts.items())),
        "max_names_per_identity": MAX_NAMES_PER_IDENTITY,
        "truncated_identity_names": truncated_identity_names,
        "model_fields": ["firstname", "middlename", "lastname"],
        "label_field": "orcid (audit grouping only)",
        "unstructured_name_fields_read": False,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.authors.open("r", encoding="utf-8") as stream:
        rows = json.load(stream)
    if not isinstance(rows, list) or not all(
        isinstance(row, Mapping) for row in rows
    ):
        raise ValueError("authors input must be a JSON list of mappings")

    result = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "sha256": _sha256(args.authors),
            "path_recorded": False,
        },
        "audit": audit(rows),
    }
    _atomic_json(args.output, result)
    print(
        "multilingual_name_coverage_complete "
        f"rows={result['audit']['rows']} "
        f"usable={result['audit']['usable_structured_rows']} "
        f"mixed_identities="
        f"{result['audit']['mixed_script_identities'].get('total', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
