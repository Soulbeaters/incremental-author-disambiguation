"""Traceable Chinese/Russian name evidence for the conditional RuZh expert.

The lexicons provide type-level evidence only.  They never assert that two
mentions are the same person and never infer a person's nationality.  The
target is a Russian-script / Chinese-name processing stratum, not an ethnicity
classifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping, Sequence


RESOURCE_ROOT = Path(__file__).with_name("resources")
CHINESE_ALIASES_PATH = RESOURCE_ROOT / "project1_chinese_surname_aliases.tsv"
RUSSIAN_LEMMAS_PATH = RESOURCE_ROOT / "opencorpora_russian_name_lemmas.tsv"
PALLADIUS_PATH = RESOURCE_ROOT / "palladius_pinyin.tsv"
FORBIDDEN_FIELDS = frozenset({"original_name"})
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

FEATURE_NAMES = (
    "query_ruzh_target",
    "profile_ruzh_target",
    "chinese_family_lexicon_match",
    "chinese_family_lexicon_conflict",
    "chinese_family_collision_risk",
    "russian_family_lemma_match",
    "russian_family_lemma_conflict",
    "russian_given_lemma_match",
    "russian_patronymic_lemma_match",
    "russian_family_gender_variant",
)

CYRILLIC_COMMON = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}
CYRILLIC_PASSPORT = {
    **CYRILLIC_COMMON,
    "й": "i",
    "ю": "iu",
    "я": "ia",
}
CYRILLIC_SIMPLIFIED = {
    **CYRILLIC_COMMON,
    "ё": "yo",
    "й": "i",
    "х": "h",
}


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0x20000 <= codepoint <= 0x2FA1F
    )


def _is_cyrillic(character: str) -> bool:
    return "CYRILLIC" in unicodedata.name(character, "")


@lru_cache(maxsize=262_144)
def _scripts(value: str) -> frozenset[str]:
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


@lru_cache(maxsize=262_144)
def _letters_key(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize(
            "NFKC", str(value or "")
        ).casefold()
        if character.isalpha()
    )


@lru_cache(maxsize=262_144)
def _tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return tuple(TOKEN_RE.findall(normalized))


def _field(record: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(record.get(name) or "").strip()
        if value:
            return value
    return ""


@lru_cache(maxsize=1)
def _chinese_aliases() -> dict[str, dict[str, frozenset[str]]]:
    aliases: dict[str, dict[str, set[str]]] = {}
    for line in CHINESE_ALIASES_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        scheme, alias, canonical_han, _share = line.split("\t")
        key = _letters_key(alias)
        aliases.setdefault(scheme, {}).setdefault(key, set()).update(
            item for item in canonical_han.split(",") if item
        )
    return {
        scheme: {
            key: frozenset(values)
            for key, values in mapping.items()
        }
        for scheme, mapping in aliases.items()
    }


@lru_cache(maxsize=1)
def _pinyin_and_palladius_syllables() -> tuple[frozenset[str], frozenset[str]]:
    pinyin: set[str] = set()
    palladius: set[str] = set()
    for line in PALLADIUS_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        pinyin_value, palladius_value = line.split("\t")
        pinyin.add(_letters_key(pinyin_value))
        palladius.add(_letters_key(palladius_value))
    return frozenset(pinyin), frozenset(palladius)


def _segmentable(value: str, syllables: frozenset[str]) -> bool:
    key = _letters_key(value)
    if not key:
        return False
    reachable = {0}
    lengths = sorted({len(item) for item in syllables})
    for position in range(len(key)):
        if position not in reachable:
            continue
        for length in lengths:
            end = position + length
            if end <= len(key) and key[position:end] in syllables:
                reachable.add(end)
    return len(key) in reachable


def _chinese_given_shape(value: str) -> bool:
    tokens = _tokens(value)
    if not tokens:
        return False
    if all(len(token) == 1 for token in tokens):
        return True
    scripts = _scripts(value)
    if "han" in scripts:
        return True
    pinyin, palladius = _pinyin_and_palladius_syllables()
    if scripts == frozenset({"latin"}):
        return all(_segmentable(token, pinyin) for token in tokens)
    if scripts == frozenset({"cyrillic"}):
        return all(_segmentable(token, palladius) for token in tokens)
    return False


@lru_cache(maxsize=262_144)
def chinese_family_candidates(value: str) -> frozenset[str]:
    scripts = _scripts(value)
    key = _letters_key(value)
    aliases = _chinese_aliases()
    schemes: tuple[str, ...]
    if "han" in scripts:
        schemes = ("han",)
    elif scripts == frozenset({"cyrillic"}):
        schemes = ("palladius",)
    elif scripts == frozenset({"latin"}):
        schemes = ("pinyin", "romanization_variant")
    else:
        return frozenset()
    return frozenset(
        canonical
        for scheme in schemes
        for canonical in aliases.get(scheme, {}).get(key, ())
    )


@lru_cache(maxsize=1)
def _russian_lemmas() -> dict[str, frozenset[str]]:
    roles: dict[str, set[str]] = {
        "given": set(),
        "patronymic": set(),
        "surname": set(),
    }
    for line in RUSSIAN_LEMMAS_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        role, lemma = line.split("\t")
        roles[role].add(lemma)
    return {role: frozenset(values) for role, values in roles.items()}


def _transliterate(value: str, mapping: Mapping[str, str]) -> str:
    return "".join(mapping.get(character, "") for character in _letters_key(value))


@lru_cache(maxsize=1)
def _russian_latin_aliases() -> dict[str, dict[str, frozenset[str]]]:
    output: dict[str, dict[str, set[str]]] = {}
    for role, lemmas in _russian_lemmas().items():
        role_aliases = output.setdefault(role, {})
        for lemma in lemmas:
            for mapping in (
                CYRILLIC_COMMON,
                CYRILLIC_PASSPORT,
                CYRILLIC_SIMPLIFIED,
            ):
                key = _transliterate(lemma, mapping)
                if key:
                    role_aliases.setdefault(key, set()).add(lemma)
    return {
        role: {
            key: frozenset(values)
            for key, values in aliases.items()
        }
        for role, aliases in output.items()
    }


def _russian_family_variants(key: str, latin: bool) -> tuple[str, ...]:
    variants = {key}
    replacements = (
        (
            ("tskaya", "tskiy"),
            ("tskaya", "tskii"),
            ("skaya", "skiy"),
            ("skaya", "skii"),
            ("skaia", "skii"),
            ("ova", "ov"),
            ("eva", "ev"),
            ("ina", "in"),
            ("yna", "yn"),
        )
        if latin
        else (
            ("цкая", "цкий"),
            ("ская", "ский"),
            ("ёва", "ёв"),
            ("ова", "ов"),
            ("ева", "ев"),
            ("ина", "ин"),
            ("ына", "ын"),
        )
    )
    for suffix, replacement in replacements:
        if key.endswith(suffix) and len(key) > len(suffix) + 1:
            variants.add(key[: -len(suffix)] + replacement)
    return tuple(sorted(variants))


@lru_cache(maxsize=262_144)
def russian_role_candidates(value: str, role: str) -> frozenset[str]:
    if role not in {"given", "patronymic", "surname"}:
        raise ValueError(f"unsupported Russian name role: {role}")
    scripts = _scripts(value)
    key = _letters_key(value)
    if not key:
        return frozenset()
    if scripts == frozenset({"cyrillic"}):
        keys = (
            _russian_family_variants(key, latin=False)
            if role == "surname"
            else (key,)
        )
        lemmas = _russian_lemmas()[role]
        return frozenset(candidate for candidate in keys if candidate in lemmas)
    if scripts == frozenset({"latin"}):
        keys = (
            _russian_family_variants(key, latin=True)
            if role == "surname"
            else (key,)
        )
        aliases = _russian_latin_aliases()[role]
        return frozenset(
            lemma for candidate in keys for lemma in aliases.get(candidate, ())
        )
    return frozenset()


def _patronymic_shape(value: str) -> bool:
    key = _letters_key(value)
    scripts = _scripts(value)
    if scripts == frozenset({"cyrillic"}):
        return key.endswith(("ович", "евич", "ич", "овна", "евна", "ична"))
    if scripts == frozenset({"latin"}):
        return key.endswith((
            "ovich", "evich", "ich", "ovna", "evna", "ichna",
        ))
    return False


@dataclass(frozen=True, slots=True)
class RuZhNameEvidence:
    target: bool
    reasons: tuple[str, ...]
    chinese_family: frozenset[str]
    russian_family: frozenset[str]
    russian_given: frozenset[str]
    russian_patronymic: frozenset[str]

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> "RuZhNameEvidence":
        leaked = FORBIDDEN_FIELDS.intersection(record)
        if leaked:
            raise ValueError(
                "RuZh evidence rejects synthetic fields: "
                f"{sorted(leaked)}"
            )
        return name_evidence(
            first=_field(record, "firstname", "first_name"),
            middle=_field(record, "middlename", "middle_name"),
            last=_field(record, "lastname", "last_name", "surname"),
        )


@lru_cache(maxsize=262_144)
def name_evidence(first: str, middle: str, last: str) -> RuZhNameEvidence:
    full = " ".join(part for part in (first, middle, last) if part)
    scripts = _scripts(full)
    chinese_family = chinese_family_candidates(last)
    russian_family = russian_role_candidates(last, "surname")
    russian_given = russian_role_candidates(first, "given")
    russian_patronymic = russian_role_candidates(middle, "patronymic")
    reasons: list[str] = []
    if "han" in scripts:
        reasons.append("han_script")
    if "cyrillic" in scripts:
        reasons.append("cyrillic_script")
    if chinese_family and _chinese_given_shape(first):
        reasons.append("chinese_family_and_given_shape")
    if russian_family and (
        russian_given or russian_patronymic or _patronymic_shape(middle)
    ):
        reasons.append("russian_name_roles")
    return RuZhNameEvidence(
        target=bool(reasons),
        reasons=tuple(reasons),
        chinese_family=chinese_family,
        russian_family=russian_family,
        russian_given=russian_given,
        russian_patronymic=russian_patronymic,
    )


def ruzh_pair_features(
    left_first: str,
    left_middle: str,
    left_last: str,
    right_first: str,
    right_middle: str,
    right_last: str,
) -> tuple[float, ...]:
    left = name_evidence(left_first, left_middle, left_last)
    right = name_evidence(right_first, right_middle, right_last)

    def match(
        left_values: frozenset[str],
        right_values: frozenset[str],
    ) -> float:
        return float(bool(left_values and right_values and (
            left_values.intersection(right_values)
        )))

    def conflict(
        left_values: frozenset[str],
        right_values: frozenset[str],
    ) -> float:
        return float(bool(left_values and right_values and not (
            left_values.intersection(right_values)
        )))

    russian_family_match = match(left.russian_family, right.russian_family)
    features = (
        float(left.target),
        float(right.target),
        match(left.chinese_family, right.chinese_family),
        conflict(left.chinese_family, right.chinese_family),
        float(max(
            len(left.chinese_family),
            len(right.chinese_family),
        ) > 1),
        russian_family_match,
        conflict(left.russian_family, right.russian_family),
        match(left.russian_given, right.russian_given),
        match(left.russian_patronymic, right.russian_patronymic),
        float(
            russian_family_match
            and _letters_key(left_last) != _letters_key(right_last)
        ),
    )
    if len(features) != len(FEATURE_NAMES):
        raise AssertionError("RuZh lexicon feature schema mismatch")
    return features


def best_profile_ruzh_features(
    query: Any,
    profile_names: Sequence[Any],
) -> tuple[float, ...]:
    """Select the strongest compatible profile view without identity labels."""

    if not profile_names:
        return (0.0,) * len(FEATURE_NAMES)
    candidates = [
        ruzh_pair_features(
            query.first,
            query.middle,
            query.last,
            profile.first,
            profile.middle,
            profile.last,
        )
        for profile in profile_names
    ]
    return max(
        candidates,
        key=lambda row: (
            row[2] + row[5] + row[7] + row[8],
            -(row[3] + row[6]),
            row,
        ),
    )


__all__ = [
    "FEATURE_NAMES",
    "RuZhNameEvidence",
    "best_profile_ruzh_features",
    "chinese_family_candidates",
    "name_evidence",
    "russian_role_candidates",
    "ruzh_pair_features",
]
