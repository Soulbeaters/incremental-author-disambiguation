# ISTINA institutional production-evidence handoff

This handoff is the remaining institution-side path from the current
research/candidate framework to a machine-verifiable release decision. It does
not authorize writes. A write-capable downstream adapter must remain absent
until the final 21-check gate reports `release_ready: true`.

## Required private inputs

The institutional operator supplies the following outside Git:

1. An adjudicated ISTINA publication-author export with exact author identity
   labels. Each publication needs a stable article ID, title, year, discipline,
   and author rows; journal, affiliation, and ORCID should be included when
   available.
2. A frozen response export from the legacy service for at least 500 known
   future mentions, so both systems are evaluated on the same cases.
3. A completed copy of
   `config/istina_provenance_manifest.template.json`, including the exact export
   filename and SHA-256, timezone-aware export time, extraction method,
   independent label audit, cross-discipline confirmation, and custodian
   approval.
4. Adjudication decisions for every issue emitted by
   `evaluation/istina_gold_readiness.py`.
5. Four retained JSON deployment attachments: shadow telemetry, online-load
   output, a completed
   `config/istina_drift_monitor_verification.template.json`, and a completed
   `config/istina_audit_retention_verification.template.json`.
6. A completed copy of
   `config/istina_deployment_evidence.template.json` that binds those four
   attachments, the exact data hash, and the exact 40-hex Git revision.

Private mention-level data, audit JSONL, service responses, and paging exports
must not be committed. Versioned artifacts should contain aggregates, redacted
identifiers, filenames, and hashes only.

## Fixed acceptance thresholds

The code revision enforces these defaults:

| Evidence | Requirement |
|---|---:|
| Strict-temporal test | at least 10,000 mentions |
| Known / genuinely unseen | at least 1,000 / 1,000 |
| Fair live shadow | at least 500 known mentions, zero writes |
| Cross-disciplinary scope | at least 5 disciplines and 3 years |
| Gold/title/year coverage | at least 95% each |
| Unresolved label issues | 0 |
| Online observation window | at least 24 hours |
| Shadow service-error rate | at most 1% |
| Online load | at least 1,000 requests |
| Online load error rate | at most 1% |
| Online load p95 | at most 20 seconds |
| Active drift monitor | at least 24 hours, paging and injected alert verified |
| Durable audit retention | at least 90 days, chain verified |

The final model-quality thresholds remain those in
`evaluation/production_gate.py`: merge precision at least 99.5%, known recall
at least 95%, automatic accuracy at least 98%, UNKNOWN at most 2%, wrong-merge
and unseen-false-link rates at most 0.1%, local p95 at most 50 ms, and a
statistically significant legacy-shadow gain of at least two percentage
points.

## Execution sequence

Run all commands from a frozen, clean revision. Replace angle-bracket values
with private paths and approved institutional identifiers.

```powershell
$revision = git rev-parse HEAD

python evaluation/istina_gold_readiness.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --provenance-manifest <private-provenance-manifest.json> --adjudication-decisions <private-adjudication-decisions.json> --adjudication-output <private-adjudication-queue.jsonl> --cleaned-output <private-cleaned-export.json> --output <private-gold-readiness.json>

python experiments/istina_runtime_replay.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --split-strategy temporal --train-through-year <frozen-year> --compact-output --output <private-temporal-replay.json>

$env:ISTINA_AUDIT_SALT = <secret-manager-value>
python experiments/istina_live_shadow.py --dataset <private-istina-export.json> --split-strategy temporal --train-through-year <frozen-year> --limit 500 --code-revision $revision --audit-output <private-retained-audit.jsonl> --output <private-live-shadow.json>

# Run only inside an approved operations window. This endpoint is read-only,
# but it intentionally generates service load and therefore requires both flags.
python experiments/istina_online_read_load.py --dataset <private-istina-export.json> --requests 1000 --concurrency 4 --max-rps 2 --man-id <approved-man-id> --code-revision $revision --approved-change-reference <change-ticket> --acknowledge-read-only-load --output <private-online-load.json>

python evaluation/istina_deployment_evidence.py --manifest <private-deployment-manifest.json> --attachment <private-live-shadow.json> <private-online-load.json> <private-drift-verification.json> <private-audit-verification.json> --expected-dataset <private-istina-export.json> --expected-code-revision $revision --output <private-deployment-validation.json>

python experiments/istina_operational_validation.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --live-shadow-evidence <private-live-shadow.json> --split-strategy temporal --train-through-year <frozen-year> --iterations 18 --tests-passed <pytest-pass-count> --test-warnings <pytest-warning-count> --output <private-operational-validation.json>

python evaluation/istina_evidence_bundle.py --operational-validation <private-operational-validation.json> --gold-readiness <private-gold-readiness.json> --live-shadow <private-live-shadow.json> --deployment-manifest <private-deployment-manifest.json> --deployment-attachment <private-live-shadow.json> <private-online-load.json> <private-drift-verification.json> <private-audit-verification.json> --expected-code-revision $revision --output <private-release-bundle.json>

python evaluation/production_gate.py --replay-result <private-operational-validation.json> --evidence <private-release-bundle.json> --output <private-production-gate.json>
```

## Fail-closed interpretation

`istina_deployment_evidence.py` ignores any hand-written `verified` field. It
recomputes 47 checks from the manifest, parses all four JSON attachments, and
compares their dataset hash, code revision, counts, rates, latency, zero-write
signals, monitoring window, paging proof, audit-chain head, retention policy,
and exact file hashes. It also requires two distinct approval references.
`istina_evidence_bundle.py` then checks that the deployment dataset hash is the
same dataset audited by gold readiness and independently reruns the attachment
checks from the raw files. The standalone deployment-validation JSON is a
preflight report, not the bundle's sole trust source. A mismatched, incomplete,
non-JSON, or edited artifact leaves online shadow, online load, and deployed
monitoring false.

The current repository evidence intentionally omits a deployment-validation
artifact because no qualifying institutional run has occurred. Therefore the
current gate must remain false.
