import subprocess
import sys
import unittest
from pathlib import Path

from evaluation.istina_evidence_bundle import (
    compose_evidence_bundle,
    revalidate_deployment_inputs,
    revalidate_paired_shadow_inputs,
)
from tests.test_istina_deployment_evidence import (
    CODE_REVISION,
    DATASET_SHA,
    valid_attachments,
    valid_manifest,
)
from tests.test_istina_paired_shadow import (
    PLAN_SHA,
    criteria_for_test as paired_criteria_for_test,
    valid_live_shadow as valid_paired_live_shadow,
    valid_plan as valid_paired_plan,
)


class IstinaEvidenceBundleTests(unittest.TestCase):
    def test_cli_requires_raw_deployment_inputs_not_prevalidated_json(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "evaluation"
            / "istina_evidence_bundle.py"
        )
        completed = subprocess.run(
            [sys.executable, str(script), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("--deployment-manifest", completed.stdout)
        self.assertIn("--deployment-attachment", completed.stdout)
        self.assertNotIn("--deployment-validation", completed.stdout)

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

    def test_bundle_revalidates_raw_attachment_contents(self):
        gold = {
            "inputs": {
                "datasets": [
                    {"name": "export.json", "sha256": DATASET_SHA}
                ]
            }
        }
        attachments = valid_attachments()

        valid = revalidate_deployment_inputs(
            gold,
            valid_manifest(),
            attachments,
            expected_code_revision=CODE_REVISION,
        )
        attachments[1]["document"]["stats"]["requests"] = 999
        tampered = revalidate_deployment_inputs(
            gold,
            valid_manifest(),
            attachments,
            expected_code_revision=CODE_REVISION,
        )

        self.assertTrue(valid["verified"])
        self.assertEqual(
            valid["validation_mode"],
            "bundle_raw_attachment_revalidation",
        )
        self.assertFalse(tampered["verified"])
        self.assertIn(
            "load_attachment_counts",
            {failure["name"] for failure in tampered["failures"]},
        )

    def test_bundle_revalidates_raw_paired_shadow_and_plan(self):
        gold = {
            "inputs": {
                "datasets": [
                    {"name": "export.json", "sha256": DATASET_SHA}
                ]
            }
        }
        live = valid_paired_live_shadow()

        valid = revalidate_paired_shadow_inputs(
            gold,
            live,
            valid_paired_plan(),
            expected_code_revision=CODE_REVISION,
            expected_plan_sha256=PLAN_SHA,
            criteria=paired_criteria_for_test(),
        )
        live["protocol"]["paired_shadow_plan_sha256"] = "d" * 64
        mismatched_plan = revalidate_paired_shadow_inputs(
            gold,
            live,
            valid_paired_plan(),
            expected_code_revision=CODE_REVISION,
            expected_plan_sha256=PLAN_SHA,
            criteria=paired_criteria_for_test(),
        )
        live["protocol"]["paired_shadow_plan_sha256"] = PLAN_SHA
        live["records"][0]["service_error"] = True
        tampered = revalidate_paired_shadow_inputs(
            gold,
            live,
            valid_paired_plan(),
            expected_code_revision=CODE_REVISION,
            expected_plan_sha256=PLAN_SHA,
            criteria=paired_criteria_for_test(),
        )

        self.assertTrue(valid["verified"])
        self.assertEqual(
            valid["validation_mode"],
            "bundle_raw_shadow_plan_revalidation",
        )
        self.assertFalse(mismatched_plan["verified"])
        self.assertIn(
            "live_plan_sha256",
            {failure["name"] for failure in mismatched_plan["failures"]},
        )
        self.assertFalse(tampered["verified"])


if __name__ == "__main__":
    unittest.main()
