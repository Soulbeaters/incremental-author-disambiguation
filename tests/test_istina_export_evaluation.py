import unittest
from types import SimpleNamespace

from experiments.istina_export_temporal_evaluation import (
    combine_local_with_structured_repair,
    combine_local_with_unknown_fallback,
    evaluate_known_author_unknown_fallback,
    evaluate_service_papers,
    exported_author_name,
    select_local_decision_mentions,
    select_service_mentions,
    split_mentions,
)


class IstinaExportEvaluationTests(unittest.TestCase):
    def test_exported_author_name_ignores_synthetic_original_name(self):
        author = {
            "lastname": "Ма",
            "firstname": "Цзясин",
            "middlename": "",
            "original_name": "Fabricated Identity",
            "name": "Another Unstructured Alias",
        }

        self.assertEqual("Ма Цзясин", exported_author_name(author))

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

    def test_local_decision_subset_uses_matching_records(self):
        mentions = [
            {"article_id": "p", "position": 1, "gold_author_id": "a"},
            {"article_id": "p", "position": 2, "gold_author_id": "b"},
        ]
        records = [
            {**mentions[0], "decision": "unknown"},
            {**mentions[1], "decision": "new"},
        ]

        selected = select_local_decision_mentions(mentions, records, "unknown", limit=10)

        self.assertEqual([1], [row["position"] for row in selected])

    def test_known_author_fallback_counts_only_safe_service_result(self):
        service_result = {"records": [
            {
                "article_id": "p1",
                "name": "Roberts C.",
                "gold_author_id": "1",
                "result_id": "1",
                "candidates": [{
                    "id": 1,
                    "last_name": "roberts",
                    "first_name": "c",
                    "middle_name": "",
                    "name_similarity": 0.85,
                }],
            },
            {
                "article_id": "p2",
                "name": "New A.",
                "gold_author_id": "2",
                "result_id": "2",
                "candidates": [{
                    "id": 2,
                    "last_name": "new",
                    "first_name": "a",
                    "middle_name": "",
                    "name_similarity": 1.0,
                }],
            },
        ]}

        result = evaluate_known_author_unknown_fallback(service_result, {"1"}, 0.85)

        self.assertEqual(result["stats"]["accepted"], 1)
        self.assertEqual(result["stats"]["correct"], 1)
        self.assertEqual(result["stats"]["wrong"], 0)

    def test_known_author_fallback_requires_local_candidate(self):
        record = {
            "article_index": 1,
            "article_id": "p",
            "position": 1,
            "name": "Polluted Alias",
            "gold_author_id": "100",
            "result_id": "100",
            "candidates": [{
                "id": 100,
                "last_name": "polluted",
                "first_name": "alias",
                "middle_name": "",
                "name_similarity": 1.0,
            }],
        }

        result = evaluate_known_author_unknown_fallback(
            {"records": [record]},
            {"100", "200"},
            0.85,
            local_candidate_ids={("1", "p", "1", "100", "Polluted Alias"): {"200"}},
        )

        self.assertEqual(result["stats"]["accepted"], 0)
        self.assertEqual(result["records"][0]["reason"], "service_result_not_local_candidate")

    def test_combined_metrics_move_only_accepted_unknowns_to_merge(self):
        local = {
            "stats": {
                "total": 100,
                "existing_gold": 20,
                "new_gold": 80,
                "merge": 10,
                "new": 80,
                "unknown": 10,
                "correct_merge": 10,
                "wrong_merge": 0,
                "correct_new": 80,
                "false_new_for_existing": 0,
                "merge_for_new_gold": 0,
            }
        }
        fallback = {"stats": {"accepted": 5, "correct": 5, "wrong": 0}}

        result = combine_local_with_unknown_fallback(local, fallback)

        self.assertEqual(result["stats"]["merge"], 15)
        self.assertEqual(result["stats"]["unknown"], 5)
        self.assertEqual(result["metrics"]["precision"], 1.0)
        self.assertEqual(result["metrics"]["existing_recall"], 0.75)

    def test_structured_repair_updates_new_and_unknown_pools(self):
        local = {
            "stats": {
                "total": 10,
                "existing_gold": 4,
                "new_gold": 6,
                "merge": 2,
                "new": 7,
                "unknown": 1,
                "correct_merge": 2,
                "wrong_merge": 0,
                "correct_new": 6,
                "false_new_for_existing": 1,
                "merge_for_new_gold": 0,
            }
        }
        repair = {"records": [
            {
                "accepted": True,
                "correct": True,
                "base_decision": "new",
                "gold_seen_in_history": True,
            },
            {
                "accepted": True,
                "correct": True,
                "base_decision": "unknown",
                "gold_seen_in_history": True,
            },
        ]}

        result = combine_local_with_structured_repair(local, repair)

        self.assertEqual(result["stats"]["merge"], 4)
        self.assertEqual(result["stats"]["new"], 6)
        self.assertEqual(result["stats"]["unknown"], 0)
        self.assertEqual(result["stats"]["false_new_for_existing"], 0)
        self.assertEqual(result["metrics"]["precision"], 1.0)

    def test_paper_service_mode_sends_full_context_and_scores_targets_only(self):
        mentions = [
            {
                "article_index": 1,
                "article_id": "p",
                "position": position,
                "gold_author_id": str(position),
                "name": f"Author {position}",
                "author": {"lastname": "Author", "firstname": str(position)},
            }
            for position in (1, 2, 3)
        ]

        class FakeClient:
            def __init__(self):
                self.request_sizes = []

            @staticmethod
            def from_exported_author(author, repair_short_family=True):
                from integrations.istina_disambiguation_client import IstinaServiceAuthor
                return IstinaServiceAuthor(author["lastname"], author["firstname"])

            def request_candidates(self, authors, man_id):
                authors = list(authors)
                self.request_sizes.append(len(authors))
                return {
                    "authors": [[{
                        "id": index,
                        "last_name": "author",
                        "first_name": str(index),
                        "middle_name": "",
                        "name_similarity": 1.0,
                    }] for index in (1, 2, 3)],
                    "authors_names": [{}, {}, {}],
                    "result_id": ["1", "2", "3"],
                }

        client = FakeClient()
        args = SimpleNamespace(man_id=1, service_sleep=0)

        result = evaluate_service_papers(
            service_mentions=[dict(mentions[0]), dict(mentions[2])],
            all_mentions=mentions,
            args=args,
            client=client,
        )

        self.assertEqual(client.request_sizes, [3])
        self.assertEqual(result["stats"]["attempted"], 2)
        self.assertEqual(result["stats"]["result_matches_gold"], 2)


if __name__ == "__main__":
    unittest.main()
