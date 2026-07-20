# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.run_evaluation import load_crossref_data  # noqa: E402
from scripts.run_evaluation_realistic import (  # noqa: E402
    load_crossref_data as load_realistic_data,
    visible_orcid,
)


class TestRunEvaluationLoader(unittest.TestCase):
    def test_load_crossref_data_accepts_jsonl_mentions(self):
        row = {
            "mention_id": "m1",
            "raw_name": "Wu Junde",
            "lastname": "Wu",
            "firstname": "Junde",
            "orcid": "0000-0000-0000-0001",
            "venue": "Test Journal",
        }

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8", delete=False) as fh:
            fh.write(json.dumps(row) + "\n")
            path = fh.name

        try:
            authors = load_crossref_data(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0]["original_name"], "Wu Junde")
        self.assertEqual(authors[0]["surname"], "Wu")
        self.assertEqual(authors[0]["journal"], "Test Journal")

    def test_realistic_loader_accepts_jsonl_mentions(self):
        row = {
            "mention_id": "m1",
            "raw_name": "Qi Wentao",
            "lastname": "Qi",
            "firstname": "Wentao",
            "orcid": "0000-0000-0000-0002",
            "venue": "Quantum Journal",
        }

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8", delete=False) as fh:
            fh.write(json.dumps(row) + "\n")
            path = fh.name

        try:
            authors = load_realistic_data(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0]["original_name"], "Qi Wentao")
        self.assertEqual(authors[0]["surname"], "Qi")
        self.assertEqual(authors[0]["journal"], "Quantum Journal")

    def test_visible_orcid_can_hide_orcid_feature(self):
        author = {"orcid": "0000-0000-0000-0002"}

        self.assertEqual(visible_orcid(author, hide_orcid_feature=False), author["orcid"])
        self.assertEqual(visible_orcid(author, hide_orcid_feature=True), "")


if __name__ == "__main__":
    unittest.main()
