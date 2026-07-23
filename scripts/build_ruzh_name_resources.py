"""Build compact, provenance-preserving name lexicons for the RuZh expert.

The builder has two deliberately separate inputs:

* Project One's MIT-licensed Chinese surname/Pinyin/Palladius resources; and
* the CC BY-SA OpenCorpora dictionary distributed by pymorphy3-dicts-ru.

Only type-level aliases and lemmas are exported.  Person identifiers,
publication records, frequencies inferred from people, and synthetic display
names never enter either artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable


ROLE_TAGS = ("Name", "Patr", "Surn")
CYRILLIC_LEMMA_RE = re.compile(r"^[а-яё-]+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, lines: Iterable[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    digest = hashlib.sha256()
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            encoded = line.encode("utf-8")
            digest.update(encoded)
            handle.write(line)
    temporary.replace(path)
    return digest.hexdigest()


def _load_project1(project1_root: Path) -> dict[str, object]:
    root = str(project1_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    modules = {
        name: importlib.import_module(f"data.{name}")
        for name in (
            "chinese_surnames",
            "surname_frequency",
            "surname_pinyin_db",
            "surname_russian_db",
            "variant_pinyin_map",
        )
    }
    return modules


def _canonical_values(values: Iterable[str]) -> str:
    return ",".join(sorted({str(value) for value in values if value}))


def chinese_alias_lines(project1_root: Path) -> tuple[list[str], dict[str, int]]:
    modules = _load_project1(project1_root)
    surnames = modules["chinese_surnames"]
    frequencies = modules["surname_frequency"]
    pinyin = modules["surname_pinyin_db"]
    palladius = modules["surname_russian_db"]
    variants = modules["variant_pinyin_map"]

    rows: set[tuple[str, str, str, str]] = set()
    for surname in surnames.ALL_SURNAMES:
        rows.add(("han", surname.casefold(), surname, "0"))

    for key, canonical in pinyin.PINYIN_TO_SURNAME.items():
        share = frequencies.get_surname_frequency_share(key.replace(" ", ""))
        rows.add((
            "pinyin",
            key.casefold(),
            _canonical_values(canonical),
            f"{share:.4f}" if share else "0",
        ))

    for key, canonical in palladius.RUSSIAN_TO_SURNAME.items():
        rows.add((
            "palladius",
            key.casefold(),
            _canonical_values(canonical),
            "0",
        ))

    for alias, normalized_keys in variants.ALL_VARIANT_MAPPINGS.items():
        canonical = {
            surname
            for normalized in normalized_keys
            for surname in pinyin.PINYIN_TO_SURNAME.get(normalized, ())
        }
        if canonical:
            rows.add((
                "romanization_variant",
                alias.casefold(),
                _canonical_values(canonical),
                "0",
            ))

    header = [
        "# scheme\talias\tcanonical_han\tpopulation_share\n",
    ]
    body = [
        "\t".join(row) + "\n"
        for row in sorted(rows)
    ]
    counts: dict[str, int] = {}
    for scheme, *_ in rows:
        counts[scheme] = counts.get(scheme, 0) + 1
    counts["total"] = len(rows)
    return header + body, dict(sorted(counts.items()))


def russian_lemma_lines() -> tuple[list[str], dict[str, int], dict[str, object]]:
    try:
        import pymorphy3
        import pymorphy3_dicts_ru
    except ImportError as error:
        raise RuntimeError(
            "Install pymorphy3 and pymorphy3-dicts-ru into the builder "
            "environment; they are not runtime dependencies."
        ) from error

    analyzer = pymorphy3.MorphAnalyzer(lang="ru")
    lemmas = {role: set() for role in ROLE_TAGS}
    for _word, tag, normal_form, *_ in analyzer.dictionary.iter_known_words():
        if not CYRILLIC_LEMMA_RE.fullmatch(normal_form):
            continue
        for role in ROLE_TAGS:
            if role in tag:
                lemmas[role].add(normal_form)

    role_names = {"Name": "given", "Patr": "patronymic", "Surn": "surname"}
    header = ["# role\tlemma\n"]
    body = [
        f"{role_names[role]}\t{lemma}\n"
        for role in ROLE_TAGS
        for lemma in sorted(lemmas[role])
    ]
    metadata_path = Path(pymorphy3_dicts_ru.get_path()) / "meta.json"
    metadata = dict(json.loads(metadata_path.read_text(encoding="utf-8")))
    counts = {
        role_names[role]: len(lemmas[role])
        for role in ROLE_TAGS
    }
    counts["total"] = sum(counts.values())
    return header + body, counts, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project1-root", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("disambiguation_engine") / "resources",
    )
    parser.add_argument("--pymorphy-wheel", type=Path)
    parser.add_argument("--dictionary-wheel", type=Path)
    args = parser.parse_args()

    chinese_lines, chinese_counts = chinese_alias_lines(args.project1_root)
    russian_lines, russian_counts, dictionary_metadata = russian_lemma_lines()
    chinese_path = args.output_root / "project1_chinese_surname_aliases.tsv"
    russian_path = args.output_root / "opencorpora_russian_name_lemmas.tsv"
    chinese_sha256 = atomic_write(chinese_path, chinese_lines)
    russian_sha256 = atomic_write(russian_path, russian_lines)

    source_files = [
        "data/chinese_surnames.py",
        "data/surname_frequency.py",
        "data/surname_pinyin_db.py",
        "data/surname_russian_db.py",
        "data/variant_pinyin_map.py",
        "LICENSE",
    ]
    manifest = {
        "schema_version": "project2_ruzh_name_resources_v1",
        "contains_person_records": False,
        "contains_identity_labels": False,
        "original_name_used": False,
        "project1": {
            "root_license": "MIT",
            "source_sha256": {
                relative: sha256_file(args.project1_root / relative)
                for relative in source_files
            },
            "output": chinese_path.name,
            "output_sha256": chinese_sha256,
            "counts": chinese_counts,
        },
        "russian_name_roles": {
            "source": "OpenCorpora via pymorphy3-dicts-ru",
            "data_license": "CC BY-SA 3.0",
            "dictionary_metadata": dictionary_metadata,
            "dictionary_wheel_sha256": (
                sha256_file(args.dictionary_wheel)
                if args.dictionary_wheel
                else None
            ),
            "pymorphy_wheel_sha256": (
                sha256_file(args.pymorphy_wheel)
                if args.pymorphy_wheel
                else None
            ),
            "output": russian_path.name,
            "output_sha256": russian_sha256,
            "counts": russian_counts,
        },
    }
    manifest_path = args.output_root / "ruzh_name_resources.manifest.json"
    manifest_sha256 = atomic_write(
        manifest_path,
        [json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"],
    )
    print(json.dumps({
        "chinese": chinese_counts,
        "russian": russian_counts,
        "manifest_sha256": manifest_sha256,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
