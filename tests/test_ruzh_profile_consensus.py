from disambiguation_engine.multilingual_name_features import StructuredName
from disambiguation_engine.ruzh_profile_consensus import (
    FEATURE_NAMES,
    profile_consensus_features,
)


def _features(query, profiles):
    return dict(zip(FEATURE_NAMES, profile_consensus_features(query, profiles)))


def test_profile_consensus_rewards_repeated_compatible_views():
    query = StructuredName("Jiaxing", "", "Ma")
    profiles = (
        StructuredName("Jia-Xing", "", "Ma"),
        StructuredName("Цзясин", "", "Ма"),
    )

    features = _features(query, profiles)

    assert features["profile_name_view_log_count"] > 1.0
    assert features["profile_name_support_mean"] > 0.8
    assert features["profile_name_support_rate_085"] == 1.0
    assert features["profile_name_conflict_rate"] == 0.0
    assert features["profile_cross_script_support_rate"] > 0.0
    assert features["profile_name_consensus_margin"] > 0.8


def test_profile_consensus_exposes_lexicon_conflicts():
    query = StructuredName("Иван", "Иванович", "Иванов")
    profiles = (
        StructuredName("Иван", "Иванович", "Иванов"),
        StructuredName("Иван", "Иванович", "Петров"),
    )

    features = _features(query, profiles)

    assert 0.5 < features["profile_name_support_mean"] < 1.0
    assert features["profile_name_conflict_rate"] == 0.5
    assert features["profile_name_consensus_margin"] < 0.2


def test_profile_consensus_empty_profile_is_zero():
    assert profile_consensus_features(
        StructuredName("Анна", "", "Иванова"),
        (),
    ) == (0.0,) * len(FEATURE_NAMES)
