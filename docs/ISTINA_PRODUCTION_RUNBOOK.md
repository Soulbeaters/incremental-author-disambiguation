# ISTINA production runbook

## Current authorization

The current branch is authorized for offline replay, live no-write shadow, and
candidate generation only. It is not authorized to write identity decisions
back to ISTINA. The latest machine gate passes 14 of 21 checks and reports
`release_ready: false`.

## Runtime boundary

Use `integrations.istina_production_runtime.IstinaProductionRuntime` around an
`IstinaDisambiguationPipeline` instance. Its default mode is `shadow`.

- `shadow`: computes decisions, optionally compares the legacy service, writes
  redacted audit telemetry, and never authorizes a downstream command.
- `candidate`: emits deterministic suggestions and idempotency keys, but every
  command remains unauthorized.
- `write`: starts only when a non-expired `ReleaseAuthorization` matches the
  full runtime commit and SHA-256 of a machine gate artifact that itself says
  `release_ready: true`.

The runtime deliberately does not contain an ISTINA write client. A downstream
adapter must reject any command whose `authorized` flag is false and must use
the supplied idempotency key to prevent duplicate mutations.

## Safe deployment sequence

1. Freeze the code revision, data hashes, legacy responses, criteria, and
   evidence artifact.
2. Run the full test suite and all three public/private frozen replays.
3. Run `experiments/istina_operational_validation.py` on the approved ISTINA
   export. Repeated load operations must not be counted as extra gold.
4. Run `experiments/istina_live_shadow.py` in no-write mode. Production release
   requires at least 500 shared, adjudicated shadow mentions.
5. Run the machine gate with the replay as `--replay-result` and the operational
   artifact as `--evidence`.
6. Deploy in `shadow`, verify online latency and drift for the agreed window,
   then progress to `candidate`.
7. Create a short-lived production authorization only after every gate passes.
   Never hand-edit `release_ready` or reuse an authorization for another commit
   or evidence hash.

## Circuit breaker and rollback

The legacy-service wrapper opens after three consecutive failures by default,
rejects further calls during the recovery timeout, permits a bounded half-open
probe, and closes only after success. A service error, open circuit, or drift
alert forces the effective runtime mode to `shadow` before commands are built.

Rollback procedure:

1. stop consuming authorized commands;
2. set the desired mode to `shadow` and revoke the release authorization;
3. retain redacted audit events, deterministic hashes, code revision, and
   evidence hashes;
4. inspect UNKNOWN/merge-rate shift, stage-distribution variation, service
   errors, candidate truncation, and p95 latency;
5. replay the affected window with the frozen revision before re-enabling
   candidate mode.

## Required alerts

The rolling monitor checks:

- UNKNOWN-rate increase;
- absolute merge-rate shift;
- total variation of decision-stage distribution;
- legacy-service error rate;
- candidate-pool truncation rate;
- local p95 latency.

An alert is a rollback signal, not permission to relax thresholds. The monitor
must be connected to the production metrics and paging system before the
`drift_monitoring_verified` gate can pass.

## Evidence still required

The available advisor export contains 1,264 test mentions but only 90 known
mentions from 88 repeated gold authors. It cannot satisfy the required 10,000
total, 1,000 known, or 500 shared-shadow thresholds. Obtain an adjudicated,
cross-disciplinary ISTINA export of the required size, then perform a 500-case
live shadow, an online end-to-end load test, and deployed drift monitoring.

Do not duplicate, resample, or repeatedly replay existing mentions to claim a
larger gold set. Until these requirements pass, the defensible production mode
is shadow/candidate and the defensible article claim is a statistically strong
improvement on the available advisor-labelled sample with explicit risk
control—not universal replacement readiness.
