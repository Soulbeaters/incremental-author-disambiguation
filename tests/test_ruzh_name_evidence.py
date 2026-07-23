import pytest

from disambiguation_engine.ruzh_name_evidence import (
    FEATURE_NAMES,
    RuZhNameEvidence,
    chinese_family_candidates,
    name_evidence,
    russian_role_candidates,
    ruzh_pair_features,
)


def test_project1_chinese_aliases_link_han_pinyin_and_palladius():
    han = chinese_family_candidates("马")
    pinyin = chinese_family_candidates("Ma")
    palladius = chinese_family_candidates("Ма")

    assert "马" in han
    assert han.intersection(pinyin)
    assert han.intersection(palladius)


def test_project1_variant_romanization_is_type_evidence():
    assert chinese_family_candidates("Cheung").intersection(
        chinese_family_candidates("Zhang")
    )


def test_russian_roles_and_gendered_surname_share_a_lemma():
    masculine = russian_role_candidates("Иванов", "surname")
    feminine = russian_role_candidates("Ivanova", "surname")

    assert "иванов" in masculine
    assert masculine.intersection(feminine)
    assert "александр" in russian_role_candidates("Aleksandr", "given")
    assert "александрович" in russian_role_candidates(
        "Aleksandrovich", "patronymic"
    )


def test_target_router_covers_chinese_russian_and_cross_script_names():
    assert name_evidence("嘉兴", "", "马").target
    assert name_evidence("Jiaxing", "", "Ma").target
    assert name_evidence("Цзясин", "", "Ма").target
    assert name_evidence("Александр", "Александрович", "Иванов").target
    assert name_evidence("Aleksandr", "Aleksandrovich", "Ivanov").target
    assert not name_evidence("Blexa", "", "Qwerton").target


def test_ruzh_boundary_rejects_fabricated_original_name():
    with pytest.raises(ValueError, match="synthetic"):
        RuZhNameEvidence.from_mapping({
            "firstname": "Jiaxing",
            "lastname": "Ma",
            "original_name": "fabricated",
        })


def test_pair_features_encode_compatibility_and_not_identity():
    features = dict(zip(
        FEATURE_NAMES,
        ruzh_pair_features(
            "Цзясин", "", "Ма",
            "Jiaxing", "", "Ma",
        ),
    ))

    assert features["query_ruzh_target"] == 1.0
    assert features["profile_ruzh_target"] == 1.0
    assert features["chinese_family_lexicon_match"] == 1.0
    assert features["chinese_family_lexicon_conflict"] == 0.0


def test_russian_gender_variant_is_a_feature_not_a_merge_rule():
    features = dict(zip(
        FEATURE_NAMES,
        ruzh_pair_features(
            "Анна", "", "Иванова",
            "Anna", "", "Ivanov",
        ),
    ))

    assert features["russian_family_lemma_match"] == 1.0
    assert features["russian_family_gender_variant"] == 1.0
