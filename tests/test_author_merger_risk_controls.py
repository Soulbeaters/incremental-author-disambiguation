# -*- coding: utf-8 -*-
import os
import sys
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disambiguation_engine.author_merger import AuthorMerger  # noqa: E402
from disambiguation_engine.decision_types import Decision  # noqa: E402
from models.database import AuthorDatabase  # noqa: E402


class TieScorer:
    def compute_comparisons(self, mention, author):
        return {
            "name_bin": "exact",
            "orcid_bin": "missing",
            "coauthor_bin": "none",
            "journal_bin": "none",
            "affiliation_bin": "none",
        }

    def score_fellegi_sunter(self, comparisons):
        return 1.0, {"name": 1.0}


class WeakNameScorer:
    def compute_comparisons(self, mention, author):
        return {
            "name_bin": "low",
            "orcid_bin": "missing",
            "coauthor_bin": "none",
            "journal_bin": "none",
            "affiliation_bin": "exact",
        }

    def score_fellegi_sunter(self, comparisons):
        return 5.0, {"affiliation": 5.0}


class OrcidMatchScorer(WeakNameScorer):
    def compute_comparisons(self, mention, author):
        comparisons = super().compute_comparisons(mention, author)
        comparisons["orcid_bin"] = "match"
        return comparisons


class TestAuthorMergerRiskControls(unittest.TestCase):
    def test_min_accept_margin_downgrades_tied_merge_to_unknown(self):
        database = AuthorDatabase()
        database.add_author({"name": "Wei Chen"})
        database.add_author({"name": "Wei Chen"})
        merger = AuthorMerger(
            database=database,
            mode="fs",
            accept_threshold=0.0,
            reject_threshold=-10.0,
            min_accept_margin=0.01,
        )
        merger.scorer = TieScorer()

        result = merger.make_decision({"name": "Wei Chen"})

        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.best_author_id)
        self.assertIn("min_accept_margin", result.reason)
        self.assertEqual(len(result.topk), 2)

    def test_low_name_without_context_downgrades_merge_to_unknown(self):
        database = AuthorDatabase()
        database.add_author({"name": "Alice Zhang", "affiliation": ["Shared Lab"]})
        merger = AuthorMerger(
            database=database,
            mode="fs",
            accept_threshold=0.0,
            reject_threshold=-10.0,
            require_context_for_low_name_accept=True,
        )
        merger.scorer = WeakNameScorer()

        result = merger.make_decision({"name": "Bob Smith", "affiliation": ["Shared Lab"]})

        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.best_author_id)
        self.assertIn("low name evidence", result.reason)

    def test_orcid_match_is_not_blocked_by_low_name_context_guard(self):
        database = AuthorDatabase()
        author = database.add_author({"name": "Alice Zhang", "orcid": "0000-0001-0000-0001"})
        merger = AuthorMerger(
            database=database,
            mode="fs",
            accept_threshold=0.0,
            reject_threshold=-10.0,
            require_context_for_low_name_accept=True,
        )
        merger.scorer = OrcidMatchScorer()

        result = merger.make_decision({
            "name": "Bob Smith",
            "orcid": "0000-0001-0000-0001",
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.best_author_id, author.author_id)


if __name__ == "__main__":
    unittest.main()
