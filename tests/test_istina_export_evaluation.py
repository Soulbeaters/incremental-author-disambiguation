import unittest

from experiments.istina_export_temporal_evaluation import (
    select_service_mentions,
    split_mentions,
)


class IstinaExportEvaluationTests(unittest.TestCase):
    def test_per_author_holdout_uses_first_repeated_mention_as_history(self):
        mentions = [
            {"gold_author_id": "a", "year": 2021, "article_index": 2, "position": 1},
            {"gold_author_id": "a", "year": 2020, "article_index": 1, "position": 1},
            {"gold_author_id": "b", "year": 2022, "article_index": 3, "position": 1},
        ]

        history, test = split_mentions(mentions, "per-author-holdout", 2023)

        self.assertEqual(["a"], [row["gold_author_id"] for row in history])
        self.assertEqual(2020, history[0]["year"])
        self.assertEqual(["a", "b"], [row["gold_author_id"] for row in test])

    def test_service_comparison_only_uses_authors_present_in_history(self):
        mentions = [
            {"gold_author_id": "seen", "position": 1},
            {"gold_author_id": "new", "position": 2},
            {"gold_author_id": None, "position": 3},
        ]

        selected = select_service_mentions(mentions, {"seen": "local-id"}, limit=10)

        self.assertEqual([1], [row["position"] for row in selected])

    def test_service_comparison_limit_is_deterministic(self):
        mentions = [
            {"gold_author_id": "seen", "position": position}
            for position in range(4)
        ]

        selected = select_service_mentions(mentions, ["seen"], limit=2)

        self.assertEqual([0, 1], [row["position"] for row in selected])


if __name__ == "__main__":
    unittest.main()
