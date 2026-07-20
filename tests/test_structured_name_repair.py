import unittest

from disambiguation_engine.structured_name_repair import (
    build_repair_profiles,
    decide_structured_repair,
    given_relation,
    structured_name_parts,
)


class StructuredNameRepairTests(unittest.TestCase):
    def test_istina_display_name_falls_back_to_family_first(self):
        family, given = structured_name_parts({"name": "Skurikhin A.V."})
        self.assertEqual(family, "skurikhin")
        self.assertEqual(given, ("a", "v"))

    def test_given_relation_supports_full_name_and_initials(self):
        self.assertEqual(
            given_relation(("vsevolod", "v"), ("v", "v")),
            "initial_compatible",
        )

    def test_prefix_repair_requires_and_uses_coauthors(self):
        profiles = build_repair_profiles([{
            "gold_author_id": "10",
            "name": "Skurikhin A.",
            "article_id": "old",
            "coauthors": ["One A.", "Two B.", "Three C."],
        }])
        decision = decide_structured_repair({
            "name": "Skurikhin A.V.",
            "article_id": "new",
            "coauthors": ["One A.", "Two B.", "Other D."],
        }, profiles)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.author_id, "10")
        self.assertEqual(decision.relation, "prefix")

    def test_different_initial_is_not_repaired(self):
        profiles = build_repair_profiles([{
            "gold_author_id": "10",
            "name": "Kumar R.",
            "article_id": "old",
            "coauthors": ["One A.", "Two B."],
        }])
        decision = decide_structured_repair({
            "name": "Kumar A.",
            "article_id": "new",
            "coauthors": ["One A.", "Two B."],
        }, profiles)
        self.assertFalse(decision.accepted)

    def test_same_paper_candidate_is_rejected(self):
        profiles = build_repair_profiles([{
            "gold_author_id": "10",
            "name": "Kumar R.",
            "article_id": "paper",
            "coauthors": ["Kumar A."],
        }])
        decision = decide_structured_repair({
            "name": "Kumar R.",
            "article_id": "paper",
            "coauthors": ["Kumar A."],
        }, profiles)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "same_paper_candidate_rejected")

    def test_conflicting_history_profile_is_quarantined(self):
        profiles = build_repair_profiles([
            {"gold_author_id": "10", "name": "Peng Peng", "article_id": "a"},
            {"gold_author_id": "10", "name": "Dawson Amanda", "article_id": "b"},
        ])
        self.assertEqual(profiles.quarantined_author_ids, ("10",))
        decision = decide_structured_repair(
            {"name": "Dawson Amanda", "article_id": "c"},
            profiles,
        )
        self.assertFalse(decision.accepted)

    def test_multiple_matching_profiles_are_ambiguous(self):
        profiles = build_repair_profiles([
            {
                "gold_author_id": "10",
                "name": "Smith John",
                "article_id": "a",
                "coauthors": ["Common Coauthor"],
            },
            {
                "gold_author_id": "11",
                "name": "Smith John",
                "article_id": "b",
                "coauthors": ["Common Coauthor"],
            },
        ])
        decision = decide_structured_repair(
            {
                "name": "Smith John",
                "article_id": "c",
                "coauthors": ["Common Coauthor"],
            },
            profiles,
        )
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "ambiguous_known_profiles")

    def test_exact_full_name_without_context_is_rejected(self):
        profiles = build_repair_profiles([{
            "gold_author_id": "10",
            "name": "Chen Wei",
            "article_id": "a",
        }])
        decision = decide_structured_repair(
            {"name": "Chen Wei", "article_id": "b"},
            profiles,
        )
        self.assertFalse(decision.accepted)


if __name__ == "__main__":
    unittest.main()
