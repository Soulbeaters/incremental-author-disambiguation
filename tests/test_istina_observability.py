import json
import tempfile
import unittest
from pathlib import Path

from integrations.istina_observability import (
    AuditIntegrityError,
    MAX_AUDIT_LINE_CHARACTERS,
    TamperEvidentJsonlAuditSink,
    verify_audit_chain,
)


def valid_event():
    return {
        "schema_version": 1,
        "article_id_hash": "a" * 16,
        "name_hash": "b" * 16,
        "position": "1",
        "decision": "merge",
        "author_id_hash": "c" * 16,
        "stage": "local_fs",
        "deterministic_hash": "d" * 16,
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


class IstinaObservabilityTests(unittest.TestCase):
    def test_chain_survives_restart_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            TamperEvidentJsonlAuditSink(path)(valid_event())
            restarted = TamperEvidentJsonlAuditSink(path)
            restarted(valid_event())

            report = verify_audit_chain(path)

            self.assertTrue(report["verified"])
            self.assertEqual(report["records"], 2)
            self.assertEqual(report["head_hash"], restarted.snapshot()["head_hash"])

    def test_tampering_is_detected_and_restart_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            TamperEvidentJsonlAuditSink(path)(valid_event())
            record = json.loads(path.read_text(encoding="utf-8"))
            record["event"]["decision"] = "unknown"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(AuditIntegrityError, "record hash mismatch"):
                verify_audit_chain(path)
            with self.assertRaises(AuditIntegrityError):
                TamperEvidentJsonlAuditSink(path)

    def test_raw_identifier_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            event = valid_event()
            event["author_id"] = "raw-private-id"

            with self.assertRaisesRegex(AuditIntegrityError, "raw identifier"):
                TamperEvidentJsonlAuditSink(Path(directory) / "audit.jsonl")(event)

    def test_free_text_rollback_reason_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            event = valid_event()
            event["rollback_reason"] = "failure for Sensitive Person"

            with self.assertRaisesRegex(AuditIntegrityError, "redacted category"):
                TamperEvidentJsonlAuditSink(Path(directory) / "audit.jsonl")(event)

    def test_incomplete_and_oversized_records_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AuditIntegrityError, "incomplete"):
                verify_audit_chain(path)

            path.write_text(
                "x" * (MAX_AUDIT_LINE_CHARACTERS + 1) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditIntegrityError, "oversized"):
                verify_audit_chain(path)

    def test_fsync_disabled_sink_does_not_claim_durability(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = TamperEvidentJsonlAuditSink(
                Path(directory) / "audit.jsonl",
                fsync=False,
            )

            self.assertFalse(sink.durable)
            self.assertFalse(sink.snapshot()["durable"])


if __name__ == "__main__":
    unittest.main()
