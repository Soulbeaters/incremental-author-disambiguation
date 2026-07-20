# ISTINA production runbook

## Current authorization

The current branch is authorized for offline replay, live no-write shadow, and
candidate generation only. It is not authorized to write identity decisions
back to ISTINA. The current machine gate passes 7 of 23 checks and reports
`release_ready: false`. The five-mention live smoke passed, but release shadow
verification remains false because it is below both the 500-mention floor and
the prospectively powered paired-comparison requirement.

A current 38-mention, 14-paper read-only live diagnostic keeps the framework at
27 correct while the incumbent changes from the frozen 24 correct to 27 correct
(current exact McNemar `p=1`). The article package records this incumbent drift
without overwriting the frozen baseline. The run has zero service errors and
zero authorized commands, but remains excluded from release evidence because
the diagnostic split has paper overlap and is below both shadow floors.

The advisor endpoint is reached directly by IP. The project client disables
`requests` environment-proxy inheritance by default because a workstation proxy
was observed returning an empty HTTP 503 for a healthy direct endpoint. Proxy
use is an explicit `IstinaDisambiguationClient(..., trust_env=True)` opt-in and
must be validated in the target environment before a collection window.

## Runtime boundary

Use `integrations.istina_production_runtime.IstinaProductionRuntime` around an
`IstinaDisambiguationPipeline` instance. Its default mode is `shadow`.

- `shadow`: computes decisions, optionally compares the legacy service, writes
  redacted audit telemetry, and never authorizes a downstream command.
- `candidate`: emits deterministic suggestions and idempotency keys, but every
  command remains unauthorized.
- `write`: starts only when a non-expired `ReleaseAuthorization` matches the
  full runtime commit and SHA-256 of a machine gate artifact that itself says
  `release_ready: true`. It additionally requires an active drift monitor, a
  non-empty private audit salt, and a callable audit sink declaring
  `durable = True`.

The runtime deliberately does not contain an ISTINA write client. A downstream
adapter must reject any command whose `authorized` flag is false and must use
the supplied idempotency key to prevent duplicate mutations.

`integrations.istina_observability.TamperEvidentJsonlAuditSink` is the reference
single-process sink. It rejects raw identity fields, writes redacted events as
an fsync-enabled SHA-256 chain, verifies the full chain on restart, and causes
the runtime to suppress commands and roll back to `shadow` on storage failure.
For multiple workers, use one chain per worker or a transactional central append
service; sharing one JSONL file between processes is unsupported.
After the observation window, use
`evaluation/istina_audit_retention.py` to stream-verify every retained worker
chain and bind it to the corresponding retained, fsync-enabled shadow telemetry.
The generated attachment contains only per-file hashes, record counts, chain
heads, and a deterministic aggregate root; it excludes private paths and audit
events. The deployment validator rejects a hand-written `chain_verified`
assertion without this machine-generated manifest.

## Safe deployment sequence

1. Freeze the code revision, data hashes, legacy responses, criteria, and
   evidence artifacts.
2. Run the gold-readiness audit with a provenance manifest bound to every exact
   input SHA-256. Exact duplicate author objects within a paper are removed
   automatically; other identity conflicts require adjudication. Missing export
   time, label semantics, independent audit, scope, or custodian approval must
   fail closed.
3. Run the full test suite and the strict temporal replay. Per-author holdout
   is diagnostic only and must not replace the zero-paper-overlap result.
4. Run `experiments/istina_operational_validation.py` on the approved ISTINA
   export from a frozen revision, with a unique `--performance-trial-id`.
   Repeated load operations must not be counted as extra gold. The report
   retains every iteration's p95 and the overall all-operation p95; only the
   latter is compared with the unchanged 50 ms acceptance threshold.
5. Before the live window, register and independently approve
   `config/istina_paired_shadow_plan.template.json`. Then run
   the `--plan-only` preflight before `experiments/istina_live_shadow.py` in
   no-write mode. The live runner must receive the same plan and refuses to
   start below its mention or paper target. Production release requires at
   least 500 shared mentions and 100 papers. The default 2-point-gain and
   10%-discordance assumptions give a 1,960-mention base, which is multiplied
   by the pre-registered paper-cluster design effect. Sampling is deterministic
   and outcome-blind: one eligible mention per required paper is selected in
   source order before the remaining target is filled in source order.
6. During an approved operations window, run the explicitly acknowledged,
   rate-limited `experiments/istina_online_read_load.py`; this is a read-only
   load generator, not a write client. Use `--approval-scope
   institutional_load_window` for formal evidence. The separate
   `user_authorized_canary` scope is capped at 20 requests and is permanently
   non-release.
7. Generate the audit-retention attachment with
   `evaluation/istina_audit_retention.py`, supplying one retained audit chain
   and one retained shadow telemetry file per worker. Then complete the
   deployment template and validate its four exact attachments with
   `evaluation/istina_deployment_evidence.py`. The 53-check validator requires
   the same dataset SHA-256 and frozen 40-hex code revision.
8. Compose operational, gold-readiness, live, and validated deployment
   artifacts with
   `evaluation/istina_evidence_bundle.py`. The bundle records each source
   SHA-256, rejects a deployment-to-gold dataset mismatch, and preserves
   fail-closed verification flags. Its release workflow must receive the raw
   deployment manifest and all four attachments so it can rerun content checks;
   it must also receive the registered paired-shadow plan and rerun
   paper-cluster-aware inference. Framework decisions in every paired
   comparison must have legacy fallback disabled; incumbent results are
   observation-only. Previously generated validation or analysis JSON is
   diagnostic convenience only.
9. Run the machine gate with the strict temporal operational replay as
   `--replay-result` and the composed bundle as `--evidence`.
10. Generate the article evidence with `evaluation/istina_paper_package.py`.
   It must pass every cross-artifact hash, split, de-duplication, metric, and
   superseded-source check before any table is copied into a manuscript.
11. Deploy in `shadow`, verify online latency and drift for the agreed window,
   then progress to `candidate`.
12. Create a short-lived production authorization only after every gate passes.
   Never hand-edit `release_ready` or reuse an authorization for another
   commit or evidence hash.

The exact institution-side inputs, fixed thresholds, and commands are in
`docs/ISTINA_INSTITUTIONAL_HANDOFF.md`. The provenance, deployment, and
drift-monitor JSON templates are deliberately invalid until completed and
approved. The audit-retention template documents the output shape, but a valid
artifact must be generated from private chains and retained telemetry rather
than hand-edited. The deployment validator parses each attachment; matching
only its filename and hash is insufficient.

## Article evidence hygiene

`evidence/runtime_validation_20260719.json` is explicitly marked
`superseded_for_istina_claims`. Its pre-cleaning ISTINA 85/90 result used 52
exact duplicate rows as independent observations and must never be restored to
the primary table or release evidence. Its old OpenAlex rows are also not
current-runtime results.

The authoritative paper artifacts are
`paper/istina_empirical_evidence_20260719.json` and
`paper/ISTINA_EMPIRICAL_EVIDENCE_20260719.md`. They bind each source SHA-256,
use the current ORCID-blind OpenAlex confirmation, a paired 27,430-mention
OpenAlex stress ablation, and paired complete 6,412-mention AMiner replays.
The OpenAlex rescue remains an ablation: on both large OpenAlex and complete
AMiner stress populations it increases recall but materially lowers precision
and increases wrong merges. Public stress populations support article claims
and model-risk analysis only; they cannot satisfy the ISTINA release gate.

## Circuit breaker and rollback

The legacy-service wrapper opens after three consecutive failures by default,
rejects further calls during the recovery timeout, permits a bounded half-open
probe, and closes only after success. A service error, open circuit, or drift
alert forces the effective runtime mode to `shadow` before commands are built.
An audit append failure also forces `shadow` and raises before a result can
expose commands to the downstream adapter.

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
must be connected to production metrics and paging before the
`drift_monitoring_verified` gate can pass.

## Evidence still required

The available advisor export contains 1,735 raw authorship rows. After removing
52 exact within-paper duplicates, the strict temporal gold test contains 571
mentions but only 5 known identities and 5 fair frozen-service comparisons. It
cannot satisfy the required 10,000 total, 1,000 known, 1,000 unseen, or 500
shared-shadow thresholds. It also lacks discipline, journal, affiliation, and
ORCID fields and has two unresolved potential label conflicts. Its current
provenance declaration passes 7 of 12 checks but lacks adjudicated-person label
semantics, a reliable export timestamp, independent audit, cross-discipline
scope, and custodian approval.

The separately located 10,000-record `ISTINA_PILOT` input is Crossref author
name/ORCID/DOI data used for name-component parsing. It is not an ISTINA
identity export and must never be substituted for the required gold set.

Obtain an adjudicated, cross-disciplinary ISTINA export of the required size,
then perform the prospectively powered live shadow (500-case floor, a
1,960-case base before the registered cluster design effect, and at least 100
papers), an online end-to-end load test, and deployed drift monitoring and
durable audit retention. Do not duplicate,
resample, or repeatedly replay existing mentions to claim a larger gold set. A
successful bounded smoke is not release-scale shadow verification.

Until these requirements pass, the defensible production mode is
shadow/candidate. The cleaned advisor sample does not establish a statistically
significant advantage over the legacy service; see
`ISTINA_AUTHOR_DISAMBIGUATION_STATUS_20260719.md` for article-safe claims.
