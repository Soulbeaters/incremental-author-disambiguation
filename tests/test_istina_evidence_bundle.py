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

    def test_data_ready_without_verified_istina_provenance_fails_closed(self):
        result = compose_evidence_bundle(
            {"operational_evidence": {}},
            {
                "data_ready": True,
                "provenance": {"verified": False},
                "dataset": {"disciplines": {"physics": 10}},
                "adjudication": {"unresolved": 0},
            },
        )

        evidence = result["operational_evidence"]["cross_domain_gold_verified"]
        self.assertFalse(evidence["verified"])
        self.assertFalse(evidence["provenance_verified"])

    def test_verified_deployment_is_used_only_when_bound_to_gold_dataset(self):
        dataset_sha = "a" * 64
        deployment = {
            "verified": True,
            "expected_dataset_sha256": dataset_sha,
            "manifest": {"dataset_sha256": dataset_sha},
            "operational_evidence": {
                "online_shadow_verified": {"verified": True, "mentions": 500},
                "online_load_test_verified": {"verified": True, "requests": 1000},
                "drift_monitoring_verified": {"verified": True},
                "durable_audit_retention_verified": {"verified": True},
            },
        }
        gold = {
            "data_ready": True,
            "provenance": {"verified": True},
            "dataset": {"disciplines": {"physics": 100}},
            "adjudication": {"unresolved": 0},
            "inputs": {"datasets": [{"name": "export.json", "sha256": dataset_sha}]},
        }

        result = compose_evidence_bundle(
            {"operational_evidence": {}},
            gold,
            deployment_validation=deployment,
        )

        self.assertTrue(result["deployment_binding"]["verified"])
        self.assertTrue(
            result["operational_evidence"]["online_shadow_verified"]["verified"]
        )
        self.assertTrue(
            result["operational_evidence"]["online_load_test_verified"]["verified"]
        )

    def test_deployment_dataset_mismatch_fails_closed(self):
        deployment = {
            "verified": True,
            "expected_dataset_sha256": "b" * 64,
            "manifest": {"dataset_sha256": "b" * 64},
            "operational_evidence": {
                "online_shadow_verified": {"verified": True},
                "online_load_test_verified": {"verified": True},
                "drift_monitoring_verified": {"verified": True},
            },
        }
        gold = {
            "inputs": {
                "datasets": [{"name": "export.json", "sha256": "a" * 64}]
            }
        }

        result = compose_evidence_bundle(
            {"operational_evidence": {}},
            gold,
            deployment_validation=deployment,
        )

        self.assertFalse(result["deployment_binding"]["verified"])
        self.assertFalse(
            result["operational_evidence"]["online_shadow_verified"]["verified"]
        )


if __name__ == "__main__":
    unittest.main()
