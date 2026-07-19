import hashlib
import json
import unittest
from datetime import datetime, timezone

from disambiguation_engine.decision_types import Decision
from integrations.istina_pipeline import (
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
    IstinaPipelineDecision,
)
from integrations.istina_production_runtime import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    DecisionDriftMonitor,
    DriftBaseline,
    DriftThresholds,
    IstinaProductionRuntime,
    ReleaseAuthorization,
    RuntimeMode,
)


def history_row(author_id, name, coauthors=None):
    parts = name.split(maxsplit=1)
    return {
        "gold_author_id": author_id,
        "author_id": author_id,
        "name": name,
        "lastname": parts[0],
        "firstname": parts[1] if len(parts) > 1 else "",
        "article_id": "history",
        "coauthors": list(coauthors or []),
    }


def telemetry_decision(
    decision=Decision.MERGE,
    stage="local_fs",
    service_error=None,
    latency_ms=1.0,
    truncated=False,
):
    return IstinaPipelineDecision(
        decision=decision,
        author_id="A1" if decision == Decision.MERGE else None,
        stage=stage,
        reason="test",
        base_decision=decision,
        local_score=1.0,
        candidate_count=1,
        scored_candidate_count=1,
        candidate_pool_truncated=truncated,
        service_error=service_error,
        latency_ms=latency_ms,
        deterministic_hash="abc123",
    )


def valid_authorization(evidence, commit_sha="f" * 40):
    return ReleaseAuthorization(
        commit_sha=commit_sha,
        evidence_sha256=hashlib.sha256(evidence).hexdigest(),
        issued_at="2026-07-19T00:00:00+00:00",
        expires_at="2026-07-20T00:00:00+00:00",
        release_ready=True,
        environment="production",
    )


class DurableAuditCollector:
    durable = True

    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)


class FailingDurableAuditSink:
    durable = True

    def __call__(self, event):
        raise OSError("simulated durable storage failure")


class IstinaProductionRuntimeTests(unittest.TestCase):
    def test_circuit_breaker_opens_and_recovers_via_half_open_probe(self):
        now = [0.0]
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=2,
                recovery_timeout_seconds=5.0,
            ),
            clock=lambda: now[0],
        )

        breaker.before_call()
        breaker.record_failure()
        breaker.before_call()
        breaker.record_failure()
        self.assertEqual(breaker.state, CircuitState.OPEN)
        with self.assertRaises(CircuitOpenError):
            breaker.before_call()

        now[0] = 6.0
        breaker.before_call()
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)
        breaker.record_success()
        self.assertEqual(breaker.state, CircuitState.CLOSED)

    def test_write_mode_rejects_missing_or_mismatched_authorization(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Sensitive Person")],
            config=IstinaPipelineConfig(use_remote_fallback=False),
        )
        with self.assertRaisesRegex(ValueError, "requires a release authorization"):
            IstinaProductionRuntime(pipeline, mode=RuntimeMode.WRITE)

        evidence = (
            b'{"release_ready": true, "summary": {"failed": 0}, '
            b'"checks": [{"name": "fixture", "passed": true}]}'
        )
        authorization = valid_authorization(evidence)
        with self.assertRaisesRegex(ValueError, "evidence hash"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.WRITE,
                authorization=authorization,
                expected_commit_sha="f" * 40,
                evidence_bytes=b"different",
                now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            )

    def test_shadow_mode_emits_only_unauthorized_idempotent_commands(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Sensitive Person", ["Known Coauthor"])],
            config=IstinaPipelineConfig(use_remote_fallback=False),
        )
        audit_events = []
        runtime = IstinaProductionRuntime(
            pipeline,
            mode=RuntimeMode.SHADOW,
            audit_salt="test-salt",
            audit_sink=audit_events.append,
        )
        article = {
            "id": "private-paper-id",
            "authors": [{
                "name": "Sensitive Person",
                "lastname": "Sensitive",
                "firstname": "Person",
            }],
        }

        first = runtime.decide_paper(article, query_service=False)
        second = runtime.decide_paper(article, query_service=False)

        self.assertTrue(first.commands)
        self.assertFalse(first.commands[0].authorized)
        self.assertEqual(
            first.commands[0].idempotency_key,
            second.commands[0].idempotency_key,
        )
        raw_audit = json.dumps(audit_events, ensure_ascii=False)
        self.assertNotIn("Sensitive Person", raw_audit)
        self.assertNotIn("private-paper-id", raw_audit)
        self.assertNotIn("author_id", audit_events[0])
        self.assertRegex(audit_events[0]["author_id_hash"], r"^[0-9a-f]{16}$")

    def test_drift_monitor_detects_unknown_and_stage_shift(self):
        baseline = DriftBaseline.from_decisions([
            telemetry_decision(),
            telemetry_decision(),
        ])
        monitor = DecisionDriftMonitor(
            baseline,
            DriftThresholds(
                min_window=2,
                max_unknown_rate_increase=0.1,
                max_merge_rate_delta=0.1,
                max_stage_total_variation=0.1,
            ),
            window_size=2,
        )

        report = monitor.observe_many([
            telemetry_decision(Decision.UNKNOWN, stage="review_guard"),
            telemetry_decision(Decision.UNKNOWN, stage="review_guard"),
        ])

        self.assertTrue(report["alert"])
        self.assertEqual(report["status"], "alert")
        self.assertIn(
            "unknown_rate_increase",
            {failure["name"] for failure in report["failures"]},
        )

    def test_write_runtime_rolls_back_before_emitting_authorized_commands(self):
        evidence = (
            b'{"release_ready": true, "summary": {"failed": 0}, '
            b'"checks": [{"name": "fixture", "passed": true}]}'
        )
        commit_sha = "f" * 40
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Known Person")],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
                enable_strict_name_repair=False,
                enable_exact_name_token_repair=False,
                enable_unique_non_cjk_initial_repair=False,
                use_remote_fallback=False,
            ),
        )
        baseline = DriftBaseline.from_decisions([telemetry_decision()])
        monitor = DecisionDriftMonitor(
            baseline,
            DriftThresholds(
                min_window=1,
                max_unknown_rate_increase=0.0,
                max_merge_rate_delta=0.0,
                max_stage_total_variation=0.0,
            ),
            window_size=1,
        )
        durable_audit = DurableAuditCollector()
        runtime = IstinaProductionRuntime(
            pipeline,
            mode=RuntimeMode.WRITE,
            monitor=monitor,
            authorization=valid_authorization(evidence, commit_sha),
            expected_commit_sha=commit_sha,
            evidence_bytes=evidence,
            audit_salt="test-write-salt",
            audit_sink=durable_audit,
            now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
        )

        result = runtime.decide_paper({
            "id": "new-paper",
            "authors": [{"lastname": "Unrelated", "firstname": "Name"}],
        }, query_service=False)

        self.assertTrue(result.rolled_back)
        self.assertEqual(result.effective_mode, RuntimeMode.SHADOW)
        self.assertIn("decision drift alert", result.rollback_reason)
        self.assertFalse(any(command.authorized for command in result.commands))
        self.assertEqual(
            durable_audit.events[0]["rollback_reason"],
            "decision_drift_alert",
        )

    def test_any_audit_sink_requires_a_non_empty_salt(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Known Person")],
            config=IstinaPipelineConfig(use_remote_fallback=False),
        )

        with self.assertRaisesRegex(ValueError, "audit sink requires"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.SHADOW,
                audit_sink=DurableAuditCollector(),
            )

    def test_write_runtime_requires_monitor_and_audit_sink(self):
        evidence = (
            b'{"release_ready": true, "summary": {"failed": 0}, '
            b'"checks": [{"name": "fixture", "passed": true}]}'
        )
        commit_sha = "f" * 40
        authorization = valid_authorization(evidence, commit_sha)
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Known Person")],
            config=IstinaPipelineConfig(use_remote_fallback=False),
        )
        with self.assertRaisesRegex(ValueError, "active drift monitor"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.WRITE,
                authorization=authorization,
                expected_commit_sha=commit_sha,
                evidence_bytes=evidence,
                now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            )

        monitor = DecisionDriftMonitor(
            DriftBaseline.from_decisions([telemetry_decision()]),
            DriftThresholds(min_window=100),
            window_size=100,
        )
        with self.assertRaisesRegex(ValueError, "redacted audit sink"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.WRITE,
                monitor=monitor,
                authorization=authorization,
                expected_commit_sha=commit_sha,
                evidence_bytes=evidence,
                audit_salt="test-write-salt",
                now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(ValueError, "durable audit sink"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.WRITE,
                monitor=monitor,
                authorization=authorization,
                expected_commit_sha=commit_sha,
                evidence_bytes=evidence,
                audit_salt="test-write-salt",
                audit_sink=lambda event: None,
                now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(ValueError, "non-empty audit salt"):
            IstinaProductionRuntime(
                pipeline,
                mode=RuntimeMode.WRITE,
                monitor=monitor,
                authorization=authorization,
                expected_commit_sha=commit_sha,
                evidence_bytes=evidence,
                audit_sink=DurableAuditCollector(),
                now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            )

    def test_audit_failure_rolls_back_and_suppresses_commands(self):
        evidence = (
            b'{"release_ready": true, "summary": {"failed": 0}, '
            b'"checks": [{"name": "fixture", "passed": true}]}'
        )
        commit_sha = "f" * 40
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Known Person")],
            config=IstinaPipelineConfig(use_remote_fallback=False),
        )
        monitor = DecisionDriftMonitor(
            DriftBaseline.from_decisions([telemetry_decision()]),
            DriftThresholds(min_window=100),
            window_size=100,
        )
        runtime = IstinaProductionRuntime(
            pipeline,
            mode=RuntimeMode.WRITE,
            monitor=monitor,
            authorization=valid_authorization(evidence, commit_sha),
            expected_commit_sha=commit_sha,
            evidence_bytes=evidence,
            audit_salt="test-write-salt",
            audit_sink=FailingDurableAuditSink(),
            now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(RuntimeError, "commands suppressed"):
            runtime.decide_paper({
                "id": "new-paper",
                "authors": [{"lastname": "Known", "firstname": "Person"}],
            }, query_service=False)

        self.assertEqual(runtime.effective_mode, RuntimeMode.SHADOW)
        self.assertEqual(runtime.rollback_reason, "audit sink failure")


if __name__ == "__main__":
    unittest.main()
