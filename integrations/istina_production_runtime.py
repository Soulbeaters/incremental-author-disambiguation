"""Production safety envelope for the ISTINA disambiguation pipeline.

The statistical pipeline deliberately remains side-effect free.  This module
adds the controls needed at the production boundary: evidence-bound write
authorization, a circuit breaker around the legacy service, rolling drift
monitoring, automatic rollback to shadow mode, redacted audit events, and
idempotent write commands for a downstream ISTINA adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from disambiguation_engine.decision_types import Decision
from integrations.istina_pipeline import (
    IstinaDisambiguationPipeline,
    IstinaPipelineDecision,
    article_mentions,
)


class RuntimeMode(str, Enum):
    """Allowed deployment modes, ordered from safest to most permissive."""

    SHADOW = "shadow"
    CANDIDATE = "candidate"
    WRITE = "write"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the legacy service circuit breaker rejects a request."""


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_timeout_seconds < 0:
            raise ValueError("recovery_timeout_seconds cannot be negative")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be positive")


class CircuitBreaker:
    """Small deterministic closed/open/half-open circuit breaker."""

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or CircuitBreakerConfig()
        self._clock = clock
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: Optional[float] = None
        self.half_open_calls = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_rejected = 0

    def before_call(self) -> None:
        now = self._clock()
        if self.state == CircuitState.OPEN:
            elapsed = now - (self.opened_at if self.opened_at is not None else now)
            if elapsed >= self.config.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
            else:
                self.total_rejected += 1
                raise CircuitOpenError("legacy service circuit is open")
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                self.total_rejected += 1
                raise CircuitOpenError("legacy service half-open probe is already in flight")
            self.half_open_calls += 1

    def record_success(self) -> None:
        self.total_successes += 1
        self.consecutive_failures = 0
        self.half_open_calls = 0
        self.opened_at = None
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.total_failures += 1
        self.consecutive_failures += 1
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls = max(0, self.half_open_calls - 1)
        if (
            self.state == CircuitState.HALF_OPEN
            or self.consecutive_failures >= self.config.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = self._clock()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_rejected": self.total_rejected,
            "opened_at_monotonic": self.opened_at,
        }


class CircuitBreakingIstinaClient:
    """Drop-in wrapper for :class:`IstinaDisambiguationClient`."""

    def __init__(self, delegate: Any, circuit_breaker: CircuitBreaker) -> None:
        self.delegate = delegate
        self.circuit_breaker = circuit_breaker

    def from_exported_author(self, *args: Any, **kwargs: Any) -> Any:
        return self.delegate.from_exported_author(*args, **kwargs)

    def request_candidates(self, *args: Any, **kwargs: Any) -> Any:
        self.circuit_breaker.before_call()
        try:
            response = self.delegate.request_candidates(*args, **kwargs)
        except Exception:
            self.circuit_breaker.record_failure()
            raise
        self.circuit_breaker.record_success()
        return response


@dataclass(frozen=True)
class DriftBaseline:
    unknown_rate: float
    merge_rate: float
    stage_distribution: Mapping[str, float]

    def __post_init__(self) -> None:
        for value in (self.unknown_rate, self.merge_rate):
            if not 0.0 <= value <= 1.0:
                raise ValueError("baseline rates must be within [0, 1]")

    @classmethod
    def from_decisions(
        cls,
        decisions: Iterable[IstinaPipelineDecision],
    ) -> "DriftBaseline":
        rows = list(decisions)
        if not rows:
            raise ValueError("at least one decision is required for a drift baseline")
        stages = Counter(row.stage for row in rows)
        total = len(rows)
        return cls(
            unknown_rate=sum(row.decision == Decision.UNKNOWN for row in rows) / total,
            merge_rate=sum(row.decision == Decision.MERGE for row in rows) / total,
            stage_distribution={key: count / total for key, count in sorted(stages.items())},
        )


@dataclass(frozen=True)
class DriftThresholds:
    min_window: int = 100
    max_unknown_rate_increase: float = 0.02
    max_merge_rate_delta: float = 0.05
    max_stage_total_variation: float = 0.15
    max_service_error_rate: float = 0.01
    max_candidate_truncation_rate: float = 0.05
    max_p95_latency_ms: float = 50.0

    def __post_init__(self) -> None:
        if self.min_window < 1:
            raise ValueError("min_window must be positive")
        for name, value in asdict(self).items():
            if name != "min_window" and value < 0:
                raise ValueError(f"{name} cannot be negative")


def _percentile(values: Iterable[float], quantile: float) -> Optional[float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


class DecisionDriftMonitor:
    """Bounded rolling telemetry window with fail-closed drift checks."""

    def __init__(
        self,
        baseline: DriftBaseline,
        thresholds: Optional[DriftThresholds] = None,
        window_size: int = 1_000,
    ) -> None:
        self.baseline = baseline
        self.thresholds = thresholds or DriftThresholds()
        if window_size < self.thresholds.min_window:
            raise ValueError("window_size must be at least min_window")
        self._window: Deque[IstinaPipelineDecision] = deque(maxlen=window_size)

    def observe(self, decision: IstinaPipelineDecision) -> Dict[str, Any]:
        self._window.append(decision)
        return self.report()

    def observe_many(
        self,
        decisions: Iterable[IstinaPipelineDecision],
    ) -> Dict[str, Any]:
        self._window.extend(decisions)
        return self.report()

    def report(self) -> Dict[str, Any]:
        rows = list(self._window)
        total = len(rows)
        if not total:
            return {
                "status": "empty",
                "alert": False,
                "window_mentions": 0,
                "checks": [],
            }

        unknown_rate = sum(row.decision == Decision.UNKNOWN for row in rows) / total
        merge_rate = sum(row.decision == Decision.MERGE for row in rows) / total
        service_error_rate = sum(bool(row.service_error) for row in rows) / total
        truncation_rate = sum(row.candidate_pool_truncated for row in rows) / total
        latency_p95 = _percentile((row.latency_ms for row in rows), 0.95) or 0.0
        stage_counts = Counter(row.stage for row in rows)
        stage_distribution = {
            key: value / total for key, value in sorted(stage_counts.items())
        }
        all_stages = set(stage_distribution) | set(self.baseline.stage_distribution)
        stage_total_variation = 0.5 * sum(
            abs(
                stage_distribution.get(stage, 0.0)
                - float(self.baseline.stage_distribution.get(stage, 0.0))
            )
            for stage in all_stages
        )
        observed = {
            "unknown_rate": unknown_rate,
            "merge_rate": merge_rate,
            "service_error_rate": service_error_rate,
            "candidate_truncation_rate": truncation_rate,
            "latency_p95_ms": latency_p95,
            "stage_total_variation": stage_total_variation,
            "stage_distribution": stage_distribution,
        }
        if total < self.thresholds.min_window:
            return {
                "status": "warming_up",
                "alert": False,
                "window_mentions": total,
                "minimum_window": self.thresholds.min_window,
                "observed": observed,
                "checks": [],
            }

        checks = [
            {
                "name": "unknown_rate_increase",
                "observed": unknown_rate - self.baseline.unknown_rate,
                "limit": self.thresholds.max_unknown_rate_increase,
                "passed": (
                    unknown_rate - self.baseline.unknown_rate
                    <= self.thresholds.max_unknown_rate_increase
                ),
            },
            {
                "name": "merge_rate_delta",
                "observed": abs(merge_rate - self.baseline.merge_rate),
                "limit": self.thresholds.max_merge_rate_delta,
                "passed": abs(merge_rate - self.baseline.merge_rate)
                <= self.thresholds.max_merge_rate_delta,
            },
            {
                "name": "stage_total_variation",
                "observed": stage_total_variation,
                "limit": self.thresholds.max_stage_total_variation,
                "passed": stage_total_variation
                <= self.thresholds.max_stage_total_variation,
            },
            {
                "name": "service_error_rate",
                "observed": service_error_rate,
                "limit": self.thresholds.max_service_error_rate,
                "passed": service_error_rate
                <= self.thresholds.max_service_error_rate,
            },
            {
                "name": "candidate_truncation_rate",
                "observed": truncation_rate,
                "limit": self.thresholds.max_candidate_truncation_rate,
                "passed": truncation_rate
                <= self.thresholds.max_candidate_truncation_rate,
            },
            {
                "name": "latency_p95_ms",
                "observed": latency_p95,
                "limit": self.thresholds.max_p95_latency_ms,
                "passed": latency_p95 <= self.thresholds.max_p95_latency_ms,
            },
        ]
        failed = [check for check in checks if not check["passed"]]
        return {
            "status": "alert" if failed else "healthy",
            "alert": bool(failed),
            "window_mentions": total,
            "observed": observed,
            "checks": checks,
            "failures": failed,
        }


@dataclass(frozen=True)
class ReleaseAuthorization:
    """Evidence-bound authorization required before write mode can start."""

    commit_sha: str
    evidence_sha256: str
    issued_at: str
    expires_at: str
    release_ready: bool
    environment: str = "production"
    schema_version: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReleaseAuthorization":
        return cls(
            schema_version=int(value.get("schema_version") or 1),
            commit_sha=str(value.get("commit_sha") or ""),
            evidence_sha256=str(value.get("evidence_sha256") or ""),
            issued_at=str(value.get("issued_at") or ""),
            expires_at=str(value.get("expires_at") or ""),
            release_ready=bool(value.get("release_ready", False)),
            environment=str(value.get("environment") or ""),
        )

    def validation_errors(
        self,
        expected_commit_sha: str,
        evidence_bytes: bytes,
        now: Optional[datetime] = None,
    ) -> Tuple[str, ...]:
        errors = []
        if self.schema_version != 1:
            errors.append("unsupported authorization schema")
        if not self.release_ready:
            errors.append("release gate did not authorize writes")
        if self.environment != "production":
            errors.append("authorization environment is not production")
        if self.commit_sha != expected_commit_sha:
            errors.append("authorization commit does not match runtime commit")
        observed_hash = hashlib.sha256(evidence_bytes).hexdigest()
        if self.evidence_sha256 != observed_hash:
            errors.append("authorization evidence hash does not match")
        try:
            evidence_document = json.loads(evidence_bytes.decode("utf-8"))
            gate_document = evidence_document.get("production_gate") or evidence_document
            evidence_release_ready = bool(gate_document.get("release_ready"))
            if not evidence_release_ready:
                errors.append("evidence artifact does not report release_ready")
            checks = gate_document.get("checks")
            if not isinstance(checks, list) or not checks:
                errors.append("evidence artifact has no machine gate checks")
            elif any(not bool(check.get("passed")) for check in checks):
                errors.append("evidence artifact contains failed machine gate checks")
            summary = gate_document.get("summary") or {}
            if int(summary.get("failed") or 0) != 0:
                errors.append("evidence artifact reports failed checks")
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            errors.append("evidence artifact is not valid release JSON")
        try:
            issued = datetime.fromisoformat(self.issued_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if current < issued:
                errors.append("authorization is not active yet")
            if current >= expires:
                errors.append("authorization has expired")
        except ValueError:
            errors.append("authorization timestamps are invalid")
        return tuple(errors)


@dataclass(frozen=True)
class WriteCommand:
    operation: str
    article_id_hash: str
    position: str
    author_id: Optional[str]
    decision_hash: str
    idempotency_key: str
    authorized: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductionPaperResult:
    decisions: Tuple[IstinaPipelineDecision, ...]
    commands: Tuple[WriteCommand, ...]
    requested_mode: RuntimeMode
    effective_mode: RuntimeMode
    rolled_back: bool
    rollback_reason: Optional[str]
    monitoring: Mapping[str, Any]
    circuit_breaker: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "commands": [command.to_dict() for command in self.commands],
            "requested_mode": self.requested_mode.value,
            "effective_mode": self.effective_mode.value,
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
            "monitoring": dict(self.monitoring),
            "circuit_breaker": dict(self.circuit_breaker),
        }


class IstinaProductionRuntime:
    """Safety controller around the side-effect-free ISTINA pipeline.

    The runtime never writes to ISTINA itself.  It emits idempotent commands;
    only a separately reviewed downstream adapter may apply commands whose
    ``authorized`` field is true.
    """

    def __init__(
        self,
        pipeline: IstinaDisambiguationPipeline,
        mode: RuntimeMode = RuntimeMode.SHADOW,
        monitor: Optional[DecisionDriftMonitor] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        authorization: Optional[ReleaseAuthorization] = None,
        expected_commit_sha: str = "",
        evidence_bytes: bytes = b"",
        audit_salt: str = "",
        audit_sink: Optional[Callable[[Mapping[str, Any]], None]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        self.pipeline = pipeline
        self.requested_mode = RuntimeMode(mode)
        self.effective_mode = self.requested_mode
        self.monitor = monitor
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.authorization = authorization
        self.expected_commit_sha = expected_commit_sha
        self.evidence_bytes = evidence_bytes
        self.audit_salt = audit_salt
        self.audit_sink = audit_sink
        self.rollback_reason: Optional[str] = None

        if self.pipeline.service_client and not isinstance(
            self.pipeline.service_client,
            CircuitBreakingIstinaClient,
        ):
            self.pipeline.service_client = CircuitBreakingIstinaClient(
                self.pipeline.service_client,
                self.circuit_breaker,
            )

        if self.requested_mode == RuntimeMode.WRITE:
            if not authorization:
                raise ValueError("write mode requires a release authorization")
            errors = authorization.validation_errors(
                expected_commit_sha,
                evidence_bytes,
                now=now,
            )
            if errors:
                raise ValueError("write authorization rejected: " + "; ".join(errors))
            if not self.monitor:
                raise ValueError("write mode requires an active drift monitor")
            if not self.audit_sink:
                raise ValueError("write mode requires a redacted audit sink")

    def force_rollback(self, reason: str) -> None:
        self.effective_mode = RuntimeMode.SHADOW
        self.rollback_reason = reason

    def _hash_identifier(self, value: Any) -> str:
        payload = f"{value}|{self.audit_salt}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def _write_command(
        self,
        mention: Mapping[str, Any],
        decision: IstinaPipelineDecision,
    ) -> Optional[WriteCommand]:
        if decision.decision == Decision.UNKNOWN:
            return None
        operation = "link_existing" if decision.decision == Decision.MERGE else "create_new"
        article_hash = self._hash_identifier(mention.get("article_id") or "unknown")
        position = str(mention.get("position") or "unknown")
        idempotency_payload = "|".join((
            article_hash,
            position,
            operation,
            str(decision.author_id or ""),
            decision.deterministic_hash,
        ))
        return WriteCommand(
            operation=operation,
            article_id_hash=article_hash,
            position=position,
            author_id=decision.author_id,
            decision_hash=decision.deterministic_hash,
            idempotency_key=hashlib.sha256(idempotency_payload.encode("utf-8")).hexdigest(),
            authorized=self.effective_mode == RuntimeMode.WRITE,
        )

    def _audit_event(
        self,
        mention: Mapping[str, Any],
        decision: IstinaPipelineDecision,
        command: Optional[WriteCommand],
    ) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "article_id_hash": self._hash_identifier(mention.get("article_id") or "unknown"),
            "name_hash": self._hash_identifier(mention.get("name") or ""),
            "position": str(mention.get("position") or "unknown"),
            "decision": decision.decision.value,
            "author_id": decision.author_id,
            "stage": decision.stage,
            "deterministic_hash": decision.deterministic_hash,
            "candidate_count": decision.candidate_count,
            "candidate_pool_truncated": decision.candidate_pool_truncated,
            "latency_ms": decision.latency_ms,
            "service_error": bool(decision.service_error),
            "requested_mode": self.requested_mode.value,
            "effective_mode": self.effective_mode.value,
            "write_authorized": bool(command and command.authorized),
            "idempotency_key": command.idempotency_key if command else None,
        }

    def decide_paper(
        self,
        article: Mapping[str, Any],
        man_id: Optional[int] = None,
        article_index: Optional[int] = None,
        service_response: Optional[Mapping[str, Any]] = None,
        query_service: bool = True,
        capture_legacy_shadow: bool = True,
    ) -> ProductionPaperResult:
        mentions = article_mentions(article, article_index=article_index)
        decisions = tuple(self.pipeline.decide_paper(
            article,
            man_id=man_id,
            article_index=article_index,
            service_response=service_response,
            query_service=query_service,
            capture_legacy_shadow=capture_legacy_shadow,
            allow_service_fallback=True,
        ))

        monitoring = self.monitor.observe_many(decisions) if self.monitor else {
            "status": "disabled",
            "alert": False,
            "window_mentions": len(decisions),
            "checks": [],
        }
        service_errors = sorted({
            decision.service_error for decision in decisions if decision.service_error
        })
        if service_errors:
            self.force_rollback("legacy service error: " + "; ".join(service_errors))
        elif bool(monitoring.get("alert")):
            failed = ", ".join(
                str(check.get("name"))
                for check in monitoring.get("failures", [])
            )
            self.force_rollback("decision drift alert: " + failed)
        elif self.circuit_breaker.state == CircuitState.OPEN:
            self.force_rollback("legacy service circuit breaker is open")

        commands = tuple(
            command
            for mention, decision in zip(mentions, decisions)
            for command in (self._write_command(mention, decision),)
            if command is not None
        )
        if self.audit_sink:
            for mention, decision in zip(mentions, decisions):
                command = self._write_command(mention, decision)
                self.audit_sink(self._audit_event(mention, decision, command))

        return ProductionPaperResult(
            decisions=decisions,
            commands=commands,
            requested_mode=self.requested_mode,
            effective_mode=self.effective_mode,
            rolled_back=self.requested_mode != self.effective_mode,
            rollback_reason=self.rollback_reason,
            monitoring=monitoring,
            circuit_breaker=self.circuit_breaker.snapshot(),
        )


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakingIstinaClient",
    "CircuitOpenError",
    "CircuitState",
    "DecisionDriftMonitor",
    "DriftBaseline",
    "DriftThresholds",
    "IstinaProductionRuntime",
    "ProductionPaperResult",
    "ReleaseAuthorization",
    "RuntimeMode",
    "WriteCommand",
]
