import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.istina_deployment_evidence import (
    _load_attachment,
    assess_deployment_evidence,
)


DATASET_SHA = "b" * 64
CODE_REVISION = "a" * 40
ATTACHMENT_FILES = [
    {"name": "shadow.json", "sha256": "1" * 64},
    {"name": "load.json", "sha256": "2" * 64},
    {"name": "drift.json", "sha256": "3" * 64},
    {"name": "audit.json", "sha256": "4" * 64},
]


def valid_attachments():
    return [
        {
            **ATTACHMENT_FILES[0],
            "document": {
                "schema_version": 1,
                "protocol": {
                    "dataset_sha256": DATASET_SHA,
                    "code_revision": CODE_REVISION,
                    "mode": "shadow",
                    "write_calls": 0,
                },
                "stats": {
                    "attempted_mentions": 500,
                    "service_errors": 5,
                    "authorized_commands": 0,
                },
                "metrics": {"service_error_rate": 0.01},
                "safety": {
                    "no_write_authorized": True,
                    "durable_audit_chain": {
                        "verified": True,
                        "retained": True,
                    },
                },
                "operational_evidence": {
                    "online_shadow_verified": {"verified": True}
                },
            },
        },
        {
            **ATTACHMENT_FILES[1],
            "document": {
                "schema_version": 1,
                "protocol": {
                    "dataset_sha256": DATASET_SHA,
                    "code_revision": CODE_REVISION,
                    "mode": "read_only_candidate_lookup",
                },
                "stats": {
                    "requests": 1000,
                    "completed": 1000,
                    "errors": 10,
                    "write_calls": 0,
                },
                "metrics": {
                    "error_rate": 0.01,
                    "latency_ms_p95": 20000.0,
                },
                "safety": {
                    "verified": True,
                    "write_client_present": False,
                    "write_calls": 0,
                },
            },
        },
        {
            **ATTACHMENT_FILES[2],
            "document": {
                "schema_version": 1,
                "source_system": "istina",
                "dataset_sha256": DATASET_SHA,
                "code_revision": CODE_REVISION,
                "generated_at": "2026-07-19T00:30:00+00:00",
                "window": {
                    "start": "2026-07-18T00:00:00+00:00",
                    "end": "2026-07-19T00:00:00+00:00",
                },
                "verification": {
                    "active": True,
                    "observation_hours": 24.0,
                    "paging_route_verified": True,
                    "injected_alert_received": True,
                    "monitor_config_sha256": "5" * 64,
                    "telemetry_source_reference": "METRICS-123",
                    "paging_test_reference": "PAGE-456",
                },
            },
        },
        {
            **ATTACHMENT_FILES[3],
            "document": {
                "schema_version": 1,
                "source_system": "istina",
                "dataset_sha256": DATASET_SHA,
                "code_revision": CODE_REVISION,
                "generated_at": "2026-07-19T00:30:00+00:00",
                "verification": {
                    "durable": True,
                    "chain_verified": True,
                    "retention_days": 90,
                    "records": 500,
                    "head_hash": "6" * 64,
                    "storage_reference": "AUDIT-STORE-123",
                    "retention_policy_reference": "RETENTION-456",
                },
            },
        },
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
            {"role": "shadow_telemetry", **ATTACHMENT_FILES[0]},
            {"role": "online_load", **ATTACHMENT_FILES[1]},
            {"role": "drift_monitor", **ATTACHMENT_FILES[2]},
            {"role": "audit_verification", **ATTACHMENT_FILES[3]},
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
            valid_attachments(),
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

    def test_complete_institutional_evidence_passes(self):
        result = self.assess(valid_manifest())

        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"], {"passed": 47, "failed": 0, "total": 47})
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
        attachments = valid_attachments()
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

    def test_manifest_numbers_must_match_attachment_contents(self):
        attachments = valid_attachments()
        attachments[1]["document"]["stats"]["errors"] = 9

        result = assess_deployment_evidence(
            valid_manifest(),
            attachments,
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

        self.assertFalse(result["verified"])
        self.assertIn(
            "load_attachment_counts",
            {failure["name"] for failure in result["failures"]},
        )

    def test_missing_attachment_document_fails_closed(self):
        attachments = valid_attachments()
        attachments[2].pop("document")

        result = assess_deployment_evidence(
            valid_manifest(),
            attachments,
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

        self.assertFalse(result["verified"])
        self.assertIn(
            "attachment_documents",
            {failure["name"] for failure in result["failures"]},
        )

    def test_duplicate_attachment_role_or_file_fails_closed(self):
        manifest = valid_manifest()
        manifest["attachments"][-1] = copy.deepcopy(manifest["attachments"][0])

        result = self.assess(manifest)

        self.assertFalse(result["verified"])
        self.assertIn(
            "attachment_cardinality",
            {failure["name"] for failure in result["failures"]},
        )

    def test_attachment_loader_parses_json_and_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            valid_path = Path(directory) / "valid.json"
            invalid_path = Path(directory) / "invalid.json"
            valid_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            invalid_path.write_text("{", encoding="utf-8")

            valid = _load_attachment(valid_path)
            invalid = _load_attachment(invalid_path)

        self.assertEqual(valid["document"], {"schema_version": 1})
        self.assertRegex(valid["sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("document", invalid)
        self.assertIn("JSONDecodeError", invalid["document_error"])

    def test_malformed_audit_count_fails_closed_without_exception(self):
        attachments = valid_attachments()
        attachments[3]["document"]["verification"]["records"] = "not-a-number"

        result = assess_deployment_evidence(
            valid_manifest(),
            attachments,
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
        )

        self.assertFalse(result["verified"])
        self.assertIn(
            "audit_attachment_references",
            {failure["name"] for failure in result["failures"]},
        )


if __name__ == "__main__":
    unittest.main()
