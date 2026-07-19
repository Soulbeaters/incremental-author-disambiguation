# ISTINA author-disambiguation: production evidence status — 2026-07-19

## Executive verdict

The project now provides a reproducible article framework and a fail-closed
shadow/candidate implementation. It is **not authorized for write-enabled
replacement of the ISTINA service**. The current machine gate passes 8 of 21
checks and records `release_ready: false`.

This revision supersedes the advisor-result interpretation in
`ISTINA_AUTHOR_DISAMBIGUATION_STATUS_20260718.md`. A data-integrity audit found
52 byte-equivalent duplicate author rows within one exported publication. The
old per-author split treated those duplicates as independent history/test
observations and therefore inflated the apparent known-author sample from 38 to
90. The previously reported 85/90 versus 35/90 result remains reproducible as a
raw-export diagnostic, but it is not valid production or primary article
evidence.

The write boundary remains mechanically closed. Write mode requires a
non-expired authorization bound to the running commit and SHA-256 of a gate
artifact whose own `release_ready` value is true. No such artifact exists.

## Evidence map

| Artifact | Purpose |
|---|---|
| `evidence/istina_advisor_export_provenance_declaration_20260719.json` | fail-closed source, identity-label, audit, scope, and custodian declaration |
| `evidence/istina_gold_readiness_20260719.json` | aggregate data-quality, leakage, coverage, and adjudication audit |
| `evidence/istina_temporal_runtime_replay_20260719.json` | primary, leakage-free temporal quality replay |
| `evidence/istina_holdout_runtime_replay_deduplicated_20260719.json` | secondary per-author diagnostic |
| `evidence/istina_live_shadow_smoke_20260719.json` | bounded real-service no-write connectivity smoke |
| `evidence/istina_operational_validation_20260719.json` | load, determinism, audit, rollback, circuit-breaker, and drift tests |
| `evidence/istina_release_evidence_bundle_20260719.json` | SHA-256-bound composition of independently generated evidence |
| `evidence/istina_production_gate_operational_20260719.json` | authoritative 21-check release decision |

Mention-level advisor records and the private adjudication queue are excluded
from Git. Committed evidence contains aggregates, redacted identifiers, input
names, and hashes only.

## Real ISTINA data audit

The advisor export contains 90 publications and 1,735 raw authorship rows.
Automatic cleaning removes only author objects that are byte-equivalent within
the same paper; it does not collapse similar names or repeated identifiers.
After this operation there are 1,683 effective mentions, including 1,300 with
gold author IDs and 1,262 distinct gold IDs.

| Data property | Observed |
|---|---:|
| Exact duplicate author rows removed | 52 |
| Gold-ID coverage | 77.24% |
| Title / year coverage | 100% / 100% |
| DOI coverage | 85.56% |
| Journal / discipline coverage | 0% / 0% |
| Affiliation / ORCID coverage | 0% / 0% |
| Distinct years | 9 |
| Unresolved potential label conflicts | 2 |
| Gold-readiness checks passed | 4 / 12 |

The private adjudication queue identifies two potential conflicting-author
identities. Resolution decisions can be supplied separately; raw review
context is never written to the committed aggregate report.

The new provenance audit passes 7 of 12 source checks and fails closed. The
file hash, ISTINA source system, publication-author record type, ISTINA author
ID namespace, extraction-method documentation, single-export consistency, and
permitted offline use are declared. Production-gold status is withheld because
the exported person IDs are not independently adjudicated identity labels, the
export timestamp is unavailable, multi-discipline scope is absent, and neither
an independent label audit nor a time-bound custodian approval is available.
Changing a filename or copying an external dataset cannot satisfy these checks.

A separate 10,000-record pilot was also located and integrity-checked. Its raw
input hash is
`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`
and its run-manifest hash is
`f9dd270fce6f5e80507535137ea26357b41a296bc7a3a9cea4ad0419c89ebdb8`.
Despite the historical `ISTINA_PILOT` run label, the rows are Crossref author
name/ORCID/DOI records and the measured task is name-component parsing, not
ISTINA person-identity disambiguation. It is real public scientific-author data
and may support parser/performance context, but it is deliberately ineligible
for the ISTINA identity-gold and release gates.

## Evaluation protocols

### Primary production protocol: temporal split

Training uses publications through 2023; later publications form the test set.
Gold-only counts are 729 history mentions and 571 test mentions. The test
contains 5 identities observed in history and 566 unseen identities. Publication
overlap is zero. Only 5 test mentions are shared with the frozen legacy-service
sample.

This protocol estimates forward-time behavior without publication leakage, but
the five known-author cases are far too few for a production claim.

### Secondary diagnostic: per-author holdout

After exact de-duplication, the deterministic holdout contains 37 history
mentions and 1,263 test mentions: 38 known and 1,225 unseen. It has 13
publications shared across history and test, so it is useful for controlled
name-variation diagnostics only and cannot replace the temporal result.

The incumbent comparison is restricted to test identities that genuinely occur
in the cleaned training history. Frozen records that became unseen after
de-duplication are excluded from the paired table.

## ISTINA results after integrity correction

| Metric | Temporal primary | Per-author diagnostic |
|---|---:|---:|
| Evaluated gold mentions | 571 | 1,263 |
| Known / unseen | 5 / 566 | 38 / 1,225 |
| Correct known merges | 1 / 5 | 28 / 38 |
| Merge precision | 100% | 100% |
| Known-author recall | 20.00% | 73.68% |
| Automatic accuracy | 94.40% | 95.96% |
| UNKNOWN rate | 4.90% | 3.25% |
| Wrong merges | 0 | 0 |
| Unseen false links | 0 | 0 |
| Local p95 latency | 12.83 ms | 3.07 ms |

The production default now disables the unique-local-surname initial heuristic.
The temporal audit showed that a historical “James A.” was wrongly merged to
the future “James Alexander”; local surname uniqueness is not global identity
evidence. The heuristic remains available only as an explicit ablation. This
change restores observed merge precision to 100% at the cost of lower recall.

On the 38 fair paired diagnostic cases, the framework is correct on 28 and the
frozen legacy service on 24. Paired cells are: both correct 18, framework only
10, legacy only 6, both incorrect 4. The exact two-sided McNemar value is
`p = 0.454498291015625`; the cleaned sample does not establish a statistically
significant advantage.

## Online shadow and operational validation

The strict temporal live smoke queried the real legacy endpoint for five known
mentions across four complete-paper requests:

- 5 runtime decisions and 0 service errors;
- 0 authorized commands and 0 write calls;
- audit redaction and the ephemeral durable hash chain passed, and the circuit
  remained closed;
- paper round-trip p95 was 15.463 seconds;
- smoke health passed, but release shadow verification failed because 5 is
  below the predeclared 500-mention minimum.

The offline no-write operational run replayed all 753 temporal test mentions
(including rows without gold) for 18 iterations:

| Operational measure | Result |
|---|---:|
| Load operations | 13,554 |
| Throughput | 201.35 mentions/s |
| Local p95 | 21.08 ms |
| Deterministic-hash mismatches | 0 |
| Runtime safety/idempotency/redaction | passed |
| Durable fsync audit hash chain / restart verification | passed (8 records) |
| Circuit open, rejection, half-open, recovery | passed |
| Automatic rollback fault path | passed |
| UNKNOWN, merge-rate, stage, service-error drift alerts | passed |

This is valid local load and failure-injection evidence. It is not an online
end-to-end load test and does not prove that the drift monitor is connected to
production telemetry or paging. The audit test uses a temporary local file and
proves redaction, append durability, hash-chain integrity, and restart
verification for the single-process sink. It does not claim deployed audit
retention; multi-worker deployment requires separate per-worker chains or a
transactional central append service.

The final repository regression command reports 178 passed tests and one
collection warning for a manual scenario class with a constructor. The ISTINA,
provenance, audit-integrity, and production-control suites are included.

## Public real-data external validation

The project also retains two public scientific-author evaluations.

The OpenAlex/ORCID-blind benchmark uses ORCID only as hidden identity gold and
removes it from runtime input. Across six deterministic seeds it evaluates
43,523 test mentions (26,537 known, 16,986 unseen). The explicit in-domain
calibrated-rescue ablation obtains 99.986% merge precision, 81.70% known recall,
83.59% automatic accuracy, 13.48% UNKNOWN, and 3 unseen false links
(0.0177%). The learned rescue is disabled in the production default.

The official AMiner KDD'18 `test_100` complete-paper split evaluates 6,412 test
mentions with zero paper overlap. The deterministic default obtains 70.02%
merge precision, 64.61% known recall, 27.65% automatic accuracy, 60.51%
UNKNOWN, and 759 wrong merges. This stress test falsifies universal
transferability and prevents presenting the strong in-domain OpenAlex result as
generic production readiness.

## Machine gate

The release gate requires at least 10,000 test mentions, 1,000 known, 1,000
unseen, and 500 fair shadow cases; merge precision at least 99.5%, recall at
least 95%, automatic accuracy at least 98%, UNKNOWN at most 2%, wrong-merge and
unseen-false-link rates at most 0.1%, and local p95 at most 50 ms. It also
requires cross-disciplinary adjudicated ISTINA gold, online no-write shadow,
online load, tested rollback, and deployed drift monitoring.

Current result: **8 passed, 13 failed, 21 total; `release_ready: false`.**

Passed checks are merge precision, wrong-merge rate, unseen false-link rate,
local p95, runtime safety contract, offline load, rollback/circuit breaker, and
drift-monitor fault testing.

Failed checks are total, known, unseen, and shadow sample sizes; known recall,
automatic accuracy, UNKNOWN; significant absolute legacy-shadow gain; paired
significance; cross-disciplinary gold; 500-case online shadow; online load; and
deployed drift monitoring.

## Defensible article claims

1. A production-oriented, three-way author-disambiguation framework was
   implemented with deterministic audit traces, a redacted durable hash chain,
   idempotent commands, evidence-bound authorization, circuit breaking,
   automatic rollback, and drift monitoring.
2. A raw-export audit found and corrected a concrete leakage mechanism that
   materially changed the ISTINA result; the cleaned primary analysis is
   reported even though it is weaker.
3. On the available cleaned advisor sample, the framework makes no observed
   wrong merge, but the strict temporal known-author sample is only five and
   recall is not production-ready.
4. Strong in-domain OpenAlex behavior does not transfer to the official AMiner
   stress test, so universal superiority is not supported.
5. Online connectivity and no-write safety are demonstrated on five cases;
   availability, latency, scale, and deployed monitoring remain unproven.

It is not defensible to claim statistically significant superiority over the
legacy service on the cleaned ISTINA sample, universal author-disambiguation
superiority, or authorization for production writes.

## Reproduction

```powershell
python -m pytest -q -p no:cacheprovider

python evaluation/istina_gold_readiness.py --dataset <advisor-export.json> --service-result <frozen-service.json> --provenance-manifest evidence/istina_advisor_export_provenance_declaration_20260719.json --adjudication-output <private-queue.jsonl> --cleaned-output <private-cleaned.json> --output evidence/istina_gold_readiness_20260719.json

python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy temporal --train-through-year 2023 --service-result <frozen-service.json> --compact-output --output evidence/istina_temporal_runtime_replay_20260719.json

python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy per-author-holdout --service-result <frozen-service.json> --compact-output --output evidence/istina_holdout_runtime_replay_deduplicated_20260719.json

$env:ISTINA_AUDIT_SALT = <secret-manager-value>
python experiments/istina_live_shadow.py --dataset <advisor-export.json> --split-strategy temporal --train-through-year 2023 --limit 5 --audit-output <private-audit.jsonl> --output evidence/istina_live_shadow_smoke_20260719.json

python experiments/istina_operational_validation.py --dataset <advisor-export.json> --service-result <frozen-service.json> --live-shadow-evidence evidence/istina_live_shadow_smoke_20260719.json --split-strategy temporal --train-through-year 2023 --iterations 18 --tests-passed 178 --test-warnings 1 --output evidence/istina_operational_validation_20260719.json

python evaluation/istina_evidence_bundle.py --operational-validation evidence/istina_operational_validation_20260719.json --gold-readiness evidence/istina_gold_readiness_20260719.json --live-shadow evidence/istina_live_shadow_smoke_20260719.json --output evidence/istina_release_evidence_bundle_20260719.json

python evaluation/production_gate.py --replay-result evidence/istina_operational_validation_20260719.json --evidence evidence/istina_release_evidence_bundle_20260719.json --output evidence/istina_production_gate_operational_20260719.json
```

## Evidence still required for replacement

Obtain an adjudicated, cross-disciplinary ISTINA export with at least 10,000
future test mentions, 1,000 verified identities already present in frozen
history, 1,000 genuine new identities, and 500 cases evaluated by both systems.
The export must include discipline and sufficient affiliation/journal context,
and all unresolved label conflicts must be adjudicated. Its provenance manifest
must bind the exact file hashes, extraction time and method, label semantics,
independent audit, cross-discipline scope, and custodian approval. Then run at
least 500 cases through live no-write shadow, perform an online end-to-end load
test, deploy durable audit retention, and connect the tested drift monitor to
production telemetry and paging. Only a fully passing gate may authorize write
mode.
