import unittest

from evaluation.istina_gold_readiness import (
    GoldReadinessCriteria,
    assess_gold_readiness,
    build_adjudication_issues,
)
from integrations.istina_export_quality import deduplicate_exact_author_rows
from experiments.istina_export_temporal_evaluation import (
    iter_mentions,
    mention_identity,
)


def author(author_id, lastname, firstname):
    return {
        "author_id": author_id,
        "lastname": lastname,
        "firstname": firstname,
        "original_name": f"{lastname} {firstname}",
    }


def compact_criteria(**overrides):
    values = {
        "min_test_mentions": 2,
        "min_existing_mentions": 1,
        "min_new_mentions": 1,
        "min_shared_shadow_mentions": 0,
        "min_disciplines": 2,
        "min_distinct_years": 2,
        "min_gold_id_coverage": 0.75,
        "min_title_coverage": 1.0,
        "min_year_coverage": 1.0,
        "max_unresolved_label_issues": 0,
    }
    values.update(overrides)
    return GoldReadinessCriteria(**values)


class IstinaGoldReadinessTests(unittest.TestCase):
    def test_temporal_readiness_counts_known_and_new_gold_without_paper_leakage(self):
        articles = [
            {
                "id": "P1",
                "title": "History paper",
                "year": 2020,
                "discipline": "Physics",
                "authors": [
                    author("A1", "Smith", "John"),
                    author("H1", "Old", "Author"),
                ],
            },
            {
                "id": "P2",
                "title": "Test paper",
                "year": 2024,
                "discipline": "Medicine",
                "authors": [
                    author("A1", "Smith", "John"),
                    author("A2", "New", "Author"),
                    author(None, "Missing", "Gold"),
                ],
            },
        ]

        service_records = {
            mention_identity(mention): {"result_id": mention.get("gold_author_id")}
            for mention in iter_mentions(articles)
            if mention.get("year") == 2024 and mention.get("gold_author_id")
        }
        report, issues = assess_gold_readiness(
            articles,
            service_records=service_records,
            criteria=compact_criteria(),
            train_through_year=2023,
        )

        self.assertTrue(report["data_ready"])
        self.assertFalse(issues)
        self.assertEqual(report["production_temporal_split"]["test_mentions"], 2)
        self.assertEqual(report["production_temporal_split"]["existing_mentions"], 1)
        self.assertEqual(report["production_temporal_split"]["new_mentions"], 1)
        self.assertEqual(
            report["production_temporal_split"]["shared_shadow_mentions"],
            1,
        )
        self.assertEqual(report["production_temporal_split"]["paper_overlap"], 0)

    def test_incompatible_same_script_families_create_private_adjudication_issue(self):
        articles = [
            {
                "id": "P1",
                "title": "One",
                "year": 2020,
                "discipline": "Physics",
                "authors": [author("A1", "Smith", "John")],
            },
            {
                "id": "P2",
                "title": "Two",
                "year": 2024,
                "discipline": "Medicine",
                "authors": [author("A1", "Zhang", "Wei")],
            },
        ]

        issues = build_adjudication_issues(articles)
        conflict = next(
            issue for issue in issues
            if issue["type"] == "potential_conflicting_author_identity"
        )
        report, _ = assess_gold_readiness(
            articles,
            criteria=compact_criteria(
                min_test_mentions=1,
                min_new_mentions=0,
            ),
            train_through_year=2023,
        )

        self.assertIn("Smith John", {profile["name"] for profile in conflict["profiles"]})
        self.assertFalse(report["data_ready"])
        self.assertEqual(report["adjudication"]["unresolved"], 1)

        resolved, _ = assess_gold_readiness(
            articles,
            decisions={conflict["issue_id"]: "corrected"},
            criteria=compact_criteria(
                min_test_mentions=1,
                min_new_mentions=0,
            ),
            train_through_year=2023,
        )
        self.assertTrue(resolved["data_ready"])

    def test_duplicate_author_id_on_same_paper_is_flagged(self):
        articles = [{
            "id": "P1",
            "title": "Duplicate",
            "year": 2024,
            "discipline": "Physics",
            "authors": [
                author("A1", "Smith", "John"),
                author("A1", "Zhang", "Wei"),
            ],
        }]

        issues = build_adjudication_issues(articles)

        self.assertIn(
            "duplicate_author_id_on_paper",
            {issue["type"] for issue in issues},
        )

    def test_exact_duplicate_author_rows_are_removed_without_adjudication(self):
        duplicate = author("A1", "Smith", "John")
        articles = [{
            "id": "P1",
            "title": "Duplicate",
            "year": 2024,
            "discipline": "Physics",
            "authors": [duplicate, dict(duplicate)],
        }]

        cleaned, removed = deduplicate_exact_author_rows(articles)
        report, issues = assess_gold_readiness(
            articles,
            criteria=compact_criteria(
                min_test_mentions=1,
                min_existing_mentions=0,
                min_new_mentions=1,
                min_disciplines=1,
                min_distinct_years=1,
            ),
            train_through_year=2023,
        )

        self.assertEqual(removed, 1)
        self.assertEqual(len(cleaned[0]["authors"]), 1)
        self.assertFalse(issues)
        self.assertEqual(
            report["dataset"]["automatic_cleaning"][
                "exact_duplicate_author_rows_removed"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
