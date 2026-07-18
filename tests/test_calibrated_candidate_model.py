import unittest

from disambiguation_engine.calibrated_candidate_model import (
    MODEL_VERSION,
    candidate_features,
    predict_probability,
    select_calibrated_candidate,
)


class CalibratedCandidateModelTests(unittest.TestCase):
    def test_frozen_model_probability_is_reproducible(self):
        candidates = [
            {
                "author_id": "A1",
                "score": 0.0,
                "components": {
                    "name": 0.0,
                    "coauthor": 0.0,
                    "journal": 0.0,
                    "affiliation": 0.0,
                    "orcid": 0.0,
                },
                "comparisons": {
                    "name_sim": 0.7,
                    "coauthor_sim": 0.0,
                    "journal_sim": 0.0,
                    "affiliation_sim": 0.0,
                    "orcid_bin": "none",
                },
            },
            {
                "author_id": "A2",
                "score": -1.0,
                "components": {},
                "comparisons": {},
            },
        ]

        features = candidate_features(
            "Hanna Almira", "local_fs", 2, candidates, candidates[0], 0
        )
        probability = predict_probability(features)
        prediction = select_calibrated_candidate(
            "Hanna Almira", "local_fs", 2, candidates
        )

        self.assertEqual(MODEL_VERSION, "openalex-orcid-blind-logit-20260719-v1")
        self.assertAlmostEqual(probability, 0.9610996180594515, places=14)
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction.author_id, "A1")
        self.assertAlmostEqual(prediction.probability, probability, places=14)


if __name__ == "__main__":
    unittest.main()
