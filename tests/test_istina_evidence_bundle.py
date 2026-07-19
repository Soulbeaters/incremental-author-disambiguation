import unittest

from evaluation.istina_evidence_bundle import compose_evidence_bundle


class IstinaEvidenceBundleTests(unittest.TestCase):
    def test_bundle_preserves_smoke_but_fails_closed_on_release_volume(self):
        operational = {
            "operational_evidence": {
                "offline_load_test_verified": {"verified": True},
            }
        }
        gold = {
            "data_ready": False,
            "dataset": {"disciplines": {}},
            "adjudication": {"unresolved": 2},
        }
        live = {
            "operational_evidence": {
                "online_shadow_verified": {
                    "verified": False,
                    "smoke_verified": True,
                    "mentions": 5,
                    "minimum_release_shadow_mentions": 500,
                }
            }
        }

        result = compose_evidence_bundle(operational, gold, live)

        evidence = result["operational_evidence"]
        self.assertTrue(evidence["offline_load_test_verified"]["verified"])
        self.assertFalse(evidence["cross_domain_gold_verified"]["verified"])
        self.assertFalse(evidence["online_shadow_verified"]["verified"])
        self.assertTrue(evidence["online_shadow_verified"]["smoke_verified"])


if __name__ == "__main__":
    unittest.main()
