"""Leakage-safe multilingual name features for the S2AND extension.

The module keeps native-script, generic Latin-transliteration and Chinese
Pinyin/Palladius views separate.  The views are model features, never hard
identity rules.  Only structured first/middle/last fields are accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping, Sequence


FEATURE_NAMES = (
    "family_native_similarity",
    "given_native_similarity",
    "family_latin_similarity",
    "given_latin_similarity",
    "family_palladius_similarity",
    "given_palladius_similarity",
    "given_initial_compatibility",
    "name_order_swap_similarity",
    "patronymic_similarity",
    "patronymic_both_observed",
    "cyrillic_pair",
    "han_pair",
    "cross_script_pair",
    "short_family_risk",
)

FORBIDDEN_FIELDS = frozenset({"original_name"})
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
MAX_PINYIN_SEGMENTATIONS = 32

CYRILLIC_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


@dataclass(frozen=True, slots=True)
class StructuredName:
    first: str
    middle: str
    last: str

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> "StructuredName":
        leaked = FORBIDDEN_FIELDS.intersection(record)
        if leaked:
            raise ValueError(
                "multilingual features reject unstructured synthetic fields: "
                f"{sorted(leaked)}"
            )
        first = _field(record, "firstname", "first_name")
        middle = _field(record, "middlename", "middle_name")
        last = _field(record, "lastname", "last_name", "surname")
        if not first or not last:
            raise ValueError(
                "multilingual features require structured first and last name"
            )
        return cls(first=first, middle=middle, last=last)

    @property
    def full(self) -> str:
        return " ".join(
            part for part in (self.first, self.middle, self.last) if part
        )


def _field(record: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(record.get(name) or "").strip()
        if value:
            return value
    return ""


def _native_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return tuple(TOKEN_RE.findall(normalized))


def _native_key(value: str) -> str:
    return "".join(_native_tokens(value))


def _is_cyrillic(character: str) -> bool:
    return "CYRILLIC" in unicodedata.name(character, "")


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0x20000 <= codepoint <= 0x2FA1F
    )


def script_inventory(value: str) -> frozenset[str]:
    scripts: set[str] = set()
    for character in unicodedata.normalize("NFKC", str(value or "")):
        if not character.isalpha():
            continue
        if _is_han(character):
            scripts.add("han")
        elif _is_cyrillic(character):
            scripts.add("cyrillic")
        elif "LATIN" in unicodedata.name(character, ""):
            scripts.add("latin")
        else:
            scripts.add("other")
    return frozenset(scripts)


def _ascii_latin(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in folded
        if "a" <= character <= "z"
    )


def _generic_latin_key(value: str) -> str:
    output: list[str] = []
    for character in unicodedata.normalize("NFKC", str(value or "")).casefold():
        if _is_cyrillic(character):
            output.append(CYRILLIC_TO_LATIN.get(character, ""))
        elif "LATIN" in unicodedata.name(character, ""):
            output.append(_ascii_latin(character))
    return "".join(output)


@lru_cache(maxsize=1)
def _palladius_mapping() -> dict[str, str]:
    resource = (
        Path(__file__).with_name("resources") / "palladius_pinyin.tsv"
    )
    mapping: dict[str, str] = {}
    for line in resource.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        pinyin, palladius = line.split("\t")
        mapping[_pinyin_key(pinyin)] = palladius
    if len(mapping) < 300:
        raise RuntimeError("Palladius resource is missing or incomplete")
    return mapping


def _pinyin_key(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", value)
        .casefold()
        .replace("u:", "v")
        .replace("ü", "v")
    )
    folded = unicodedata.normalize("NFKD", normalized)
    return "".join(
        character
        for character in folded
        if ("a" <= character <= "z") or character == "v"
    )


def _han_pinyin_syllables(value: str) -> tuple[str, ...]:
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError as exc:  # pragma: no cover - research dependency guard
        raise RuntimeError(
            "Han name features require pypinyin; "
            "install requirements-training.txt"
        ) from exc
    syllables = lazy_pinyin(
        value,
        style=Style.NORMAL,
        strict=True,
        errors=lambda text: [text],
    )
    return tuple(
        key
        for item in syllables
        if (key := _pinyin_key(str(item)))
    )


@lru_cache(maxsize=65_536)
def _segment_pinyin_token(token: str) -> tuple[tuple[str, ...], ...]:
    normalized = _pinyin_key(token)
    if not normalized:
        return ()
    syllables = tuple(
        sorted(_palladius_mapping(), key=lambda item: (-len(item), item))
    )

    @lru_cache(maxsize=None)
    def visit(position: int) -> tuple[tuple[str, ...], ...]:
        if position == len(normalized):
            return ((),)
        output: list[tuple[str, ...]] = []
        for syllable in syllables:
            if not normalized.startswith(syllable, position):
                continue
            for tail in visit(position + len(syllable)):
                output.append((syllable, *tail))
                if len(output) >= MAX_PINYIN_SEGMENTATIONS:
                    return tuple(output)
        return tuple(output)

    return visit(0)


def _latin_views(value: str) -> frozenset[str]:
    scripts = script_inventory(value)
    views = {_generic_latin_key(value)}
    if "han" in scripts:
        views.add("".join(_han_pinyin_syllables(value)))
    return frozenset(view for view in views if view)


def _palladius_views(value: str) -> frozenset[str]:
    scripts = script_inventory(value)
    if "cyrillic" in scripts and "han" not in scripts:
        key = _native_key(value)
        return frozenset((key,)) if key else frozenset()

    if "han" in scripts:
        sequences = (_han_pinyin_syllables(value),)
    elif "latin" in scripts:
        tokens = _native_tokens(value)
        token_options = [
            _segment_pinyin_token(token)
            for token in tokens
        ]
        if not token_options or any(not options for options in token_options):
            return frozenset()
        sequences = tuple(
            item
            for combination in product(*token_options)
            for item in (tuple(
                syllable
                for token_sequence in combination
                for syllable in token_sequence
            ),)
        )[:MAX_PINYIN_SEGMENTATIONS]
    else:
        return frozenset()

    mapping = _palladius_mapping()
    return frozenset(
        "".join(mapping[syllable] for syllable in sequence)
        for sequence in sequences
        if sequence and all(syllable in mapping for syllable in sequence)
    )


def _levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1]
                + (left_character != right_character),
            ))
        previous = current
    return previous[-1]


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return 1.0 - (_levenshtein(left, right) / max(len(left), len(right)))


def _max_similarity(
    left_views: Sequence[str],
    right_views: Sequence[str],
) -> float:
    return max(
        (
            _similarity(left, right)
            for left in left_views
            for right in right_views
        ),
        default=0.0,
    )


def _native_similarity(left: str, right: str) -> float:
    return _similarity(_native_key(left), _native_key(right))


def _latin_similarity(left: str, right: str) -> float:
    return _max_similarity(_latin_views(left), _latin_views(right))


def _palladius_similarity(left: str, right: str) -> float:
    left_scripts = script_inventory(left)
    right_scripts = script_inventory(right)
    if (
        ("cyrillic" in left_scripts)
        == ("cyrillic" in right_scripts)
    ):
        return 0.0
    if not (
        {"latin", "han"}.intersection(left_scripts | right_scripts)
    ):
        return 0.0
    return _max_similarity(
        _palladius_views(left),
        _palladius_views(right),
    )


def _any_similarity(left: str, right: str) -> float:
    return max(
        _native_similarity(left, right),
        _latin_similarity(left, right),
        _palladius_similarity(left, right),
    )


def _initial_compatibility(left: StructuredName, right: StructuredName) -> float:
    first_score = _max_similarity(
        tuple(view[:1] for view in _latin_views(left.first) if view),
        tuple(view[:1] for view in _latin_views(right.first) if view),
    )
    if not left.middle or not right.middle:
        return first_score
    middle_score = _max_similarity(
        tuple(view[:1] for view in _latin_views(left.middle) if view),
        tuple(view[:1] for view in _latin_views(right.middle) if view),
    )
    return (first_score + middle_score) / 2.0


def multilingual_name_features(
    left: StructuredName,
    right: StructuredName,
) -> tuple[float, ...]:
    left_scripts = script_inventory(left.full)
    right_scripts = script_inventory(right.full)
    patronymic_observed = bool(left.middle and right.middle)
    left_family_length = len(_native_key(left.last))
    right_family_length = len(_native_key(right.last))

    features = (
        _native_similarity(left.last, right.last),
        _native_similarity(left.first, right.first),
        _latin_similarity(left.last, right.last),
        _latin_similarity(left.first, right.first),
        _palladius_similarity(left.last, right.last),
        _palladius_similarity(left.first, right.first),
        _initial_compatibility(left, right),
        (
            _any_similarity(left.first, right.last)
            + _any_similarity(left.last, right.first)
        )
        / 2.0,
        (
            _any_similarity(left.middle, right.middle)
            if patronymic_observed
            else 0.0
        ),
        float(patronymic_observed),
        float(
            "cyrillic" in left_scripts
            and "cyrillic" in right_scripts
        ),
        float("han" in left_scripts and "han" in right_scripts),
        float(bool(left_scripts and right_scripts and not (
            left_scripts.intersection(right_scripts)
        ))),
        float(
            min(left_family_length, right_family_length) <= 2
            or (
                ("han" in left_scripts and left_family_length <= 1)
                or ("han" in right_scripts and right_family_length <= 1)
            )
        ),
    )
    if len(features) != len(FEATURE_NAMES):
        raise AssertionError("multilingual feature schema mismatch")
    return features


def best_profile_name_features(
    query: StructuredName,
    profile_names: Sequence[StructuredName],
) -> tuple[float, ...]:
    """Return the best observed profile-name view without using identity labels."""

    if not profile_names:
        return (0.0,) * len(FEATURE_NAMES)
    candidates = [
        multilingual_name_features(query, profile)
        for profile in profile_names
    ]
    return max(
        candidates,
        key=lambda row: (
            row[2] + row[3] + row[4] + row[5],
            row[0] + row[1],
            row,
        ),
    )


__all__ = [
    "FEATURE_NAMES",
    "StructuredName",
    "best_profile_name_features",
    "multilingual_name_features",
    "script_inventory",
]
