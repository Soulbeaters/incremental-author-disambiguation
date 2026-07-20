import unittest

from experiments.openalex_runtime_replay import (
    slice_metrics,
    split_article_holdout,
    split_orcid_author_holdout,
)


class OpenAlexRuntimeReplayTests(unittest.TestCase):
    def test_orcid_holdout_is_deterministic_and_has_no_paper_overlap(self):
        mentions = [
            {
                "article_id": f"{author}-{paper}",
                "gold_author_id": author,
                "year": 2020 + paper,
                "position": 1,
            }
            for author in ("O1", "O2", "O3", "O4")
            for paper in (1, 2, 3)
        ]
        first = split_orcid_author_holdout(mentions, 0.5)
        second = split_orcid_author_holdout(mentions, 0.5)
        self.assertEqual(first, second)
        history, test = first
        self.assertFalse(
            {row["article_id"] for row in history}
            & {row["article_id"] for row in test}
        )

    def test_article_holdout_never_splits_a_paper(self):
        mentions = [
            {"article_id": "P1", "gold_author_id": "A1", "year": 2020, "position": 1},
            {"article_id": "P1", "gold_author_id": "A2", "year": 2020, "position": 2},
            {"article_id": "P2", "gold_author_id": "A1", "year": 2021, "position": 1},
            {"article_id": "P2", "gold_author_id": "A3", "year": 2021, "position": 2},
        ]
        history, test = split_article_holdout(mentions)
        self.assertEqual({row["article_id"] for row in history}, {"P1"})
        self.assertEqual({row["article_id"] for row in test}, {"P2"})
        self.assertFalse(
            {row["article_id"] for row in history}
            & {row["article_id"] for row in test}
        )

    def test_orcid_holdout_can_use_two_history_papers_per_known_author(self):
        mentions = [
            {
                "article_id": f"{author}-{paper}",
                "gold_author_id": author,
                "year": 2020 + paper,
                "position": 1,
            }
            for author in ("O1", "O2", "O3", "O4")
            for paper in (1, 2, 3, 4)
        ]
        history, test = split_orcid_author_holdout(
            mentions,
            known_author_fraction=0.9999,
            history_papers_per_known_author=2,
        )
        history_by_author = {}
        for row in history:
            history_by_author.setdefault(row["gold_author_id"], set()).add(row["article_id"])
        self.assertTrue(history_by_author)
        self.assertTrue(all(len(papers) == 2 for papers in history_by_author.values()))
        self.assertFalse(
            {row["article_id"] for row in history}
            & {row["article_id"] for row in test}
        )

    def test_slice_metrics_reports_existing_recall_and_wrong_merge(self):
        mentions = [
            {"domain": "Health", "field": "Medicine", "name_split_source": "given_first"},
            {"domain": "Health", "field": "Medicine", "name_split_source": "given_first"},
        ]
        records = [
            {
                "gold_seen_in_history": True,
                "correct": True,
                "decision": "merge",
                "author_id": "A1",
                "gold_author_id": "A1",
            },
            {
                "gold_seen_in_history": False,
                "correct": False,
                "decision": "merge",
                "author_id": "A1",
                "gold_author_id": "A2",
            },
        ]
        result = slice_metrics(mentions, records)["domain"]["Health"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["wrong_merge"], 1)
        self.assertEqual(result["existing_recall"], 1.0)
        self.assertEqual(result["merge_precision"], 0.5)


if __name__ == "__main__":
    unittest.main()
