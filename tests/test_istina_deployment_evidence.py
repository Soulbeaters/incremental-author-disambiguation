import copy
import unittest

from evaluation.istina_deployment_evidence import assess_deployment_evidence


DATASET_SHA = "b" * 64
CODE_REVISION = "a" * 40
ATTACHMENTS = [
    {"name": "shadow.json", "sha256": "1" * 64},
    {"name": "load.json", "sha256": "2" * 64},
    {"name": "drift.json", "sha256": "3" * 64},
    {"name": "audit.json", "sha256": "4" * 64},
]


def valid_manifest():
    return {
        "schema_version": 1,
        "source_system": "istina",
        "environment": "production",
        "dataset_sha256": DATASET_SHA,
        "code_revision": CODE_REVISION,
        "window": {
            "start": "2026-07-18T00:00:00+00:00",
            "end": "2026-07-19T00:00:00+00:00",
        },
        "shadow": {"mentions": 500, "write_calls": 0, "service_errors": 5},
        "online_load": {
            "requests": 1000,
            "errors": 10,
            "p95_latency_ms": 20000.0,
        },
        "drift_monitoring": {
            "active": True,
            "observation_hours": 24.0,
            "paging_route_verified": True,
            "injected_alert_received": True,
        },
        "audit": {
            "durable": True,
            "chain_verified": True,
            "retention_days": 90,
        },
        "attachments": [
            {"role": "shadow_telemetry", **ATTACHMENTS[0]},
            {"role": "online_load", **ATTACHMENTS[1]},
            {"role": "drift_monitor", **ATTACHMENTS[2]},
            {"role": "audit_verification", **ATTACHMENTS[3]},
        ],
        "approval": {
            "operations_reference": "OPS-123",
            "independent_review_reference": "RISK-456",
            "approved_at": "2026-07-19T01:00:00+00:00",
        },
    }


class IstinaDeploymentEvidenceTests(unittest.TestCase):
    def assess(self, manifest):
        return assess_deployment_evidence(
            manifest,
            ATTACHMENTS,
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

    def test_complete_institutional_evidence_passes(self):
        result = self.assess(valid_manifest())

        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"], {"passed": 28, "failed": 0, "total": 28})
        self.assertTrue(
            result["operational_evidence"]["online_shadow_verified"]["verified"]
        )

    def test_any_shadow_write_fails_closed(self):
        manifest = valid_manifest()
        manifest["shadow"]["write_calls"] = 1

        result = self.assess(manifest)

        self.assertFalse(result["verified"])
        self.assertIn(
            "shadow_write_calls",
            {failure["name"] for failure in result["failures"]},
        )

    def test_attachment_hash_mismatch_fails_closed(self):
        attachments = copy.deepcopy(ATTACHMENTS)
        attachments[0]["sha256"] = "f" * 64

        result = assess_deployment_evidence(
            valid_manifest(),
            attachments,
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

        self.assertFalse(result["verified"])
        self.assertIn(
            "attachment_hashes",
            {failure["name"] for failure in result["failures"]},
        )

    def test_dataset_or_code_mismatch_fails_closed(self):
        manifest = valid_manifest()
        manifest["dataset_sha256"] = "c" * 64
        manifest["code_revision"] = "d" * 40

        result = self.assess(manifest)
        failures = {failure["name"] for failure in result["failures"]}

        self.assertFalse(result["verified"])
        self.assertIn("dataset_sha256", failures)
        self.assertIn("code_revision", failures)


if __name__ == "__main__":
    unittest.main()
