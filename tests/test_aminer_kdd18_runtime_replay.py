import json
import tempfile
import unittest
from pathlib import Path

from experiments.aminer_kdd18_runtime_replay import (
    load_aminer_mentions,
    split_complete_papers,
    tagged_publication_parts,
)


class AminerKdd18RuntimeReplayTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        labels = {
            "john_smith": {
                "A1": ["p1-0", "p2-0"],
                "A2": ["p3-1"],
            }
        }
        publications = {
            "p1": {
                "authors": [
                    {"id": "A1", "name": "John Smith", "org": "Alpha Lab"},
                    {"id": "C1", "name": "Alice Jones", "org": "Alpha Lab"},
                ],
                "venue": "Journal A",
                "year": 2018,
            },
            "p2": {
                "authors": [
                    {"id": "A1", "name": "J. Smith", "org": "Alpha Lab"},
                    {"id": "C2", "name": "Bob Brown", "org": "Alpha Lab"},
                ],
                "venue": "Journal B",
                "year": 2020,
            },
            "p3": {
                "authors": [
                    {"id": "C3", "name": "Carol White", "org": "Beta Lab"},
                    {"id": "A2", "name": "John Smith", "org": "Beta Lab"},
                ],
                "venue": "Journal C",
                "year": 2021,
            },
        }
        (root / "name_to_pubs_test_100.json").write_text(
            json.dumps(labels), encoding="utf-8"
        )
        (root / "pubs_raw.json").write_text(
            json.dumps(publications), encoding="utf-8"
        )

    def test_tagged_publication_parts_uses_zero_based_position(self):
        self.assertEqual(tagged_publication_parts("paper-id-12"), ("paper-id", 12))

    def test_loader_validates_labels_and_preserves_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            mentions, metadata = load_aminer_mentions(root)

        self.assertEqual(len(mentions), 3)
        self.assertEqual(metadata["integrity"]["validated_mentions"], 3)
        self.assertEqual(mentions[0]["lastname"], "smith")
        self.assertEqual(mentions[0]["firstname"], "john")
        self.assertEqual(mentions[0]["coauthors"], ["Alice Jones"])
        self.assertEqual(mentions[0]["affiliation"], "Alpha Lab")

    def test_complete_paper_splits_have_no_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            mentions, _ = load_aminer_mentions(root)

        for policy in ("first-history", "last-test"):
            history, test = split_complete_papers(mentions, policy)
            self.assertFalse(
                {row["article_id"] for row in history}
                & {row["article_id"] for row in test}
            )
            self.assertEqual(len(history) + len(test), 3)

    def test_loader_rejects_label_position_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            labels_path = root / "name_to_pubs_test_100.json"
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            labels["john_smith"]["A1"][0] = "p1-1"
            labels_path.write_text(json.dumps(labels), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match author"):
                load_aminer_mentions(root)


if __name__ == "__main__":
    unittest.main()
