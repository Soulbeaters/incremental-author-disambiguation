import json
import tempfile
import unittest
from pathlib import Path

from evaluation.istina_audit_retention import (
    AUDIT_CHAIN_MANIFEST_ALGORITHM,
    AUDIT_HEAD_HASH_SCOPE,
    AUDIT_RETENTION_METHOD,
    CHAIN_ENTRY_FIELDS,
    audit_chain_manifest_sha256,
    build_audit_retention_evidence,
)
from integrations.istina_observability import (
    AuditIntegrityError,
    TamperEvidentJsonlAuditSink,
)


DATASET_SHA256 = "b" * 64
CODE_REVISION = "a" * 40


def audit_event(marker="a"):
    return {
        "schema_version": 1,
        "article_id_hash": marker * 16,
        "name_hash": "b" * 16,
        "position": "1",
        "decision": "merge",
        "author_id_hash": "c" * 16,
        "stage": "local_fs",
        "deterministic_hash": marker * 16,
        "candidate_count": 1,
        "candidate_pool_truncated": False,
        "latency_ms": 1.25,
        "service_error": False,
        "requested_mode": "shadow",
        "effective_mode": "shadow",
        "write_authorized": False,
        "idempotency_key": "e" * 64,
        "monitor_status": "healthy",
        "monitor_alert": False,
        "rollback_reason": None,
        "circuit_state": "closed",
    }


def make_chain_and_telemetry(directory, worker, records):
    chain_path = Path(directory) / f"private-worker-{worker}.jsonl"
    sink = TamperEvidentJsonlAuditSink(chain_path, fsync=True)
    for index in range(records):
        marker = format(worker + index + 1, "x")[-1]
        sink(audit_event(marker))
    snapshot = sink.snapshot()
    telemetry_path = Path(directory) / f"private-telemetry-{worker}.json"
    telemetry_path.write_text(
        json.dumps({
            "schema_version": 1,
            "protocol": {
                "dataset_sha256": DATASET_SHA256,
                "code_revision": CODE_REVISION,
                "mode": "shadow",
            },
            "safety": {
                "durable_audit_chain": {
                    "verified": True,
                    "retained": True,
                    "fsync": True,
                    "chain_records_total": snapshot["records"],
                    "head_hash": snapshot["head_hash"],
                }
            },
        }),
        encoding="utf-8",
    )
    return chain_path, telemetry_path


class IstinaAuditRetentionTests(unittest.TestCase):
    def build(self, chains, telemetry):
        return build_audit_retention_evidence(
            audit_chains=chains,
            shadow_telemetry=telemetry,
            dataset_sha256=DATASET_SHA256,
            code_revision=CODE_REVISION,
            retention_days=90,
            storage_reference="AUDIT-STORE-123",
            retention_policy_reference="RETENTION-456",
            generated_at="2026-07-20T00:00:00+00:00",
        )

    def test_multiple_worker_chains_are_stream_verified_and_aggregated(self):
        with tempfile.TemporaryDirectory() as directory:
            first = make_chain_and_telemetry(directory, 1, 1)
            second = make_chain_and_telemetry(directory, 2, 2)

            result = self.build(
                [first[0], second[0]],
                [second[1], first[1]],
            )

        proof = result["verification"]
        self.assertTrue(proof["chain_verified"])
        self.assertTrue(proof["durable"])
        self.assertEqual(proof["verification_method"], AUDIT_RETENTION_METHOD)
        self.assertEqual(
            proof["chain_manifest_algorithm"],
            AUDIT_CHAIN_MANIFEST_ALGORITHM,
        )
        self.assertEqual(proof["head_hash_scope"], AUDIT_HEAD_HASH_SCOPE)
        self.assertEqual(proof["chain_count"], 2)
        self.assertEqual(proof["telemetry_count"], 2)
        self.assertEqual(proof["records"], 3)
        self.assertFalse(proof["record_level_content_included"])
        self.assertEqual(
            proof["chain_manifest_sha256"],
            audit_chain_manifest_sha256(proof["chain_entries"]),
        )
        self.assertEqual(proof["head_hash"], proof["chain_manifest_sha256"])
        self.assertTrue(
            all(set(entry) == CHAIN_ENTRY_FIELDS for entry in proof["chain_entries"])
        )
        serialized = json.dumps(result)
        self.assertNotIn("private-worker", serialized)
        self.assertNotIn("private-telemetry", serialized)

    def test_ephemeral_telemetry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            chain, telemetry = make_chain_and_telemetry(directory, 1, 1)
            document = json.loads(telemetry.read_text(encoding="utf-8"))
            document["safety"]["durable_audit_chain"]["retained"] = False
            telemetry.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Ephemeral|ephemeral"):
                self.build([chain], [telemetry])

    def test_chain_to_telemetry_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            chain, telemetry = make_chain_and_telemetry(directory, 1, 1)
            document = json.loads(telemetry.read_text(encoding="utf-8"))
            document["safety"]["durable_audit_chain"]["head_hash"] = "f" * 64
            telemetry.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                self.build([chain], [telemetry])

    def test_tampered_chain_fails_before_evidence_is_emitted(self):
        with tempfile.TemporaryDirectory() as directory:
            chain, telemetry = make_chain_and_telemetry(directory, 1, 1)
            record = json.loads(chain.read_text(encoding="utf-8"))
            record["event"]["decision"] = "unknown"
            chain.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaises(AuditIntegrityError):
                self.build([chain], [telemetry])

    def test_retention_below_release_minimum_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            chain, telemetry = make_chain_and_telemetry(directory, 1, 1)

            with self.assertRaisesRegex(ValueError, "at least 90"):
                build_audit_retention_evidence(
                    audit_chains=[chain],
                    shadow_telemetry=[telemetry],
                    dataset_sha256=DATASET_SHA256,
                    code_revision=CODE_REVISION,
                    retention_days=89,
                    storage_reference="AUDIT-STORE-123",
                    retention_policy_reference="RETENTION-456",
                )


if __name__ == "__main__":
    unittest.main()
