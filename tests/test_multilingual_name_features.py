import pytest

from disambiguation_engine.multilingual_name_features import (
    FEATURE_NAMES,
    StructuredName,
    best_profile_name_features,
    multilingual_name_features,
    script_inventory,
)


def feature_map(left, right):
    return dict(zip(FEATURE_NAMES, multilingual_name_features(left, right)))


def test_structured_boundary_rejects_synthetic_unstructured_name():
    with pytest.raises(ValueError, match="synthetic"):
        StructuredName.from_mapping({
            "firstname": "Jiaxing",
            "lastname": "Ma",
            "original_name": "fabricated",
        })


def test_generic_cyrillic_latin_view_preserves_native_view():
    cyrillic = StructuredName(
        first="Андрей",
        middle="Александрович",
        last="Зензинов",
    )
    latin = StructuredName(
        first="Andrey",
        middle="Aleksandrovich",
        last="Zenzinov",
    )
    features = feature_map(cyrillic, latin)

    assert features["family_native_similarity"] < 0.2
    assert features["family_latin_similarity"] == 1.0
    assert features["given_latin_similarity"] == 1.0
    assert features["cross_script_pair"] == 1.0
    assert features["patronymic_both_observed"] == 1.0


def test_han_pinyin_view_matches_without_erasing_script_identity():
    han = StructuredName(first="嘉兴", middle="", last="马")
    pinyin = StructuredName(first="Jiaxing", middle="", last="Ma")
    features = feature_map(han, pinyin)

    assert script_inventory(han.full) == frozenset({"han"})
    assert features["family_latin_similarity"] == 1.0
    assert features["given_latin_similarity"] == 1.0
    assert features["cross_script_pair"] == 1.0
    assert features["short_family_risk"] == 1.0


def test_palladius_view_recovers_russian_written_chinese_name():
    palladius = StructuredName(first="Цзясин", middle="", last="Ма")
    pinyin = StructuredName(first="Jiaxing", middle="", last="Ma")
    features = feature_map(palladius, pinyin)

    assert features["family_palladius_similarity"] == 1.0
    assert features["given_palladius_similarity"] == 1.0
    assert features["cross_script_pair"] == 1.0
    assert features["short_family_risk"] == 1.0


def test_name_order_swap_is_a_feature_not_an_identity_rule():
    surname_first = StructuredName(first="Jiaxing", middle="", last="Ma")
    reversed_fields = StructuredName(first="Ma", middle="", last="Jiaxing")
    features = feature_map(surname_first, reversed_fields)

    assert features["name_order_swap_similarity"] == 1.0
    assert features["family_native_similarity"] < 1.0


def test_best_profile_view_is_deterministic_and_label_free():
    query = StructuredName(first="Цзясин", middle="", last="Ма")
    profiles = (
        StructuredName(first="Unrelated", middle="", last="Person"),
        StructuredName(first="Jiaxing", middle="", last="Ma"),
    )

    first = best_profile_name_features(query, profiles)
    second = best_profile_name_features(query, tuple(reversed(profiles)))

    assert first == second
    values = dict(zip(FEATURE_NAMES, first))
    assert values["given_palladius_similarity"] == 1.0
    assert len(first) == len(FEATURE_NAMES)
