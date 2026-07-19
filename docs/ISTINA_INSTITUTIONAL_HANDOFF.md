# ISTINA institutional production-evidence handoff

This handoff is the remaining institution-side path from the current
research/candidate framework to a machine-verifiable release decision. It does
not authorize writes. A write-capable downstream adapter must remain absent
until the final 22-check gate reports `release_ready: true`.

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
5. A completed, statistician-approved copy of
   `config/istina_paired_shadow_plan.template.json`, registered before the
   shadow window begins.
6. Four retained JSON deployment attachments: shadow telemetry, online-load
   output, a completed
   `config/istina_drift_monitor_verification.template.json`, and a completed
   `config/istina_audit_retention_verification.template.json`.
7. A completed copy of
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
| Fair live shadow | at least 500 known mentions and 100 papers, zero writes |
| Powered paired comparison | maximum of the 500 floor, registered minimum, and cluster-adjusted computed requirement |
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
points. With the default registered assumptions (`alpha=0.05`, 80% power,
2-point gain, and 10% anticipated discordance), the paired normal-approximation
base requirement is 1,960 mentions. The final collection target is this base
multiplied by the statistician-approved, pre-registered paper-cluster design
effect, rounded up, and cannot be below either the 500 floor or the registered
minimum. Final inference also requires an exact two-sided McNemar p-value at
most 0.05, a paper-cluster sign-flip p-value at most 0.05, and a paper-cluster
bootstrap interval whose lower bound is above zero. Changing assumptions after
observing outcomes invalidates the evidence.

## Execution sequence

Run all commands from a frozen, clean revision. Replace angle-bracket values
with private paths and approved institutional identifiers.

```powershell
$revision = git rev-parse HEAD

python evaluation/istina_gold_readiness.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --provenance-manifest <private-provenance-manifest.json> --adjudication-decisions <private-adjudication-decisions.json> --adjudication-output <private-adjudication-queue.jsonl> --cleaned-output <private-cleaned-export.json> --output <private-gold-readiness.json>

python experiments/istina_runtime_replay.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --split-strategy temporal --train-through-year <frozen-year> --compact-output --output <private-temporal-replay.json>

# Complete and approve the paired-shadow plan before starting the live window.
python evaluation/istina_paired_shadow.py --plan-only --plan <private-paired-shadow-plan.json> --expected-dataset <private-istina-export.json> --expected-code-revision $revision --output <private-paired-shadow-preflight.json>

$env:ISTINA_AUDIT_SALT = <secret-manager-value>
python experiments/istina_live_shadow.py --dataset <private-istina-export.json> --split-strategy temporal --train-through-year <frozen-year> --limit <preflight-effective-required-mentions> --code-revision $revision --paired-shadow-plan <private-paired-shadow-plan.json> --audit-output <private-retained-audit.jsonl> --output <private-live-shadow.json>

python evaluation/istina_paired_shadow.py --live-shadow <private-live-shadow.json> --plan <private-paired-shadow-plan.json> --expected-dataset <private-istina-export.json> --expected-code-revision $revision --output <private-paired-shadow-analysis.json>

# Run only inside an approved operations window. This endpoint is read-only,
# but it intentionally generates service load and therefore requires both flags.
python experiments/istina_online_read_load.py --dataset <private-istina-export.json> --requests 1000 --concurrency 4 --max-rps 2 --man-id <approved-man-id> --code-revision $revision --approved-change-reference <change-ticket> --acknowledge-read-only-load --output <private-online-load.json>

python evaluation/istina_deployment_evidence.py --manifest <private-deployment-manifest.json> --attachment <private-live-shadow.json> <private-online-load.json> <private-drift-verification.json> <private-audit-verification.json> --expected-dataset <private-istina-export.json> --expected-code-revision $revision --output <private-deployment-validation.json>

python experiments/istina_operational_validation.py --dataset <private-istina-export.json> --service-result <private-frozen-legacy.json> --live-shadow-evidence <private-live-shadow.json> --split-strategy temporal --train-through-year <frozen-year> --iterations 18 --tests-passed <pytest-pass-count> --test-warnings <pytest-warning-count> --output <private-operational-validation.json>

python evaluation/istina_evidence_bundle.py --operational-validation <private-operational-validation.json> --gold-readiness <private-gold-readiness.json> --live-shadow <private-live-shadow.json> --deployment-manifest <private-deployment-manifest.json> --deployment-attachment <private-live-shadow.json> <private-online-load.json> <private-drift-verification.json> <private-audit-verification.json> --paired-shadow-plan <private-paired-shadow-plan.json> --expected-code-revision $revision --output <private-release-bundle.json>

python evaluation/production_gate.py --replay-result <private-operational-validation.json> --evidence <private-release-bundle.json> --output <private-production-gate.json>
```

When the plan is supplied, the live runner makes the sample deterministic and
outcome-blind: it first selects one eligible known-author mention from each
required distinct paper in source order, then fills the remaining target in
source order. It refuses to contact the service if the plan, hashes, code
revision, mention target, or available paper coverage is insufficient.

## Fail-closed interpretation

`istina_deployment_evidence.py` ignores any hand-written `verified` field. It
recomputes 47 checks from the manifest, parses all four JSON attachments, and
compares their dataset hash, code revision, counts, rates, latency, zero-write
signals, monitoring window, paging proof, audit-chain head, retention policy,
and exact file hashes. It also requires two distinct approval references.
`istina_evidence_bundle.py` then checks that the deployment dataset hash is the
same dataset audited by gold readiness and independently reruns the attachment
checks from the raw files. It also reruns the 39-check paired analysis directly
from live records and the registered plan, including the plan file hash,
cluster-adjusted collection target, and minimum paper count recorded by the
live runner. Standalone validation, preflight, and analysis JSON files are
diagnostic reports, not the bundle's trust source. A mismatched, incomplete,
non-JSON, or edited artifact leaves online shadow, online load, paired
comparison, and deployed monitoring false.

The current repository evidence intentionally omits a deployment-validation
artifact because no qualifying institutional run has occurred. Therefore the
current gate must remain false.
