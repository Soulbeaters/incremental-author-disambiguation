# ISTINA author-disambiguation: production evidence status — 2026-07-19

## Executive verdict

The project now provides a reproducible article framework and a fail-closed
shadow/candidate implementation. It is **not authorized for write-enabled
replacement of the ISTINA service**. The current machine gate passes 8 of 23
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
| `evidence/istina_live_shadow_diagnostic_20260720.json` | current-service 38-case real-service diagnostic with explicit incumbent drift; ineligible for release gates |
| `evidence/istina_online_read_load_canary_20260720.json` | four-request, concurrency-two real-service load-path canary; explicitly non-release |
| `evidence/istina_operational_validation_20260719.json` | load, determinism, audit, rollback, circuit-breaker, and drift tests |
| `evidence/istina_operational_validation_trial[1-3]_20260720.json` | three frozen-revision sequential offline performance trials with per-iteration p95 |
| `evidence/istina_offline_performance_reproducibility_20260720.json` | all-trials-must-pass, path-free repeatability aggregate |
| `evidence/istina_release_evidence_bundle_20260719.json` | SHA-256-bound composition of independently generated evidence |
| `evidence/istina_production_gate_operational_20260719.json` | authoritative 23-check release decision |
| `evaluation/istina_audit_retention.py` | stream-verifies retained per-worker audit chains and binds them to fsync shadow telemetry |
| `evaluation/istina_deployment_evidence.py` | 55-check, content-level institutional shadow/load-plan/load/monitor/audit validator |
| `evaluation/istina_online_load_plan.py` | immutable institutional load-plan preflight and execution-binding validator |
| `evaluation/istina_revision_binding.py` | fail-fast verification that the declared 40-hex revision is the executing Git HEAD |
| `evaluation/istina_paired_shadow.py` | preflighted cluster-adjusted power, exact McNemar, paper-cluster randomization and bootstrap analysis |
| `experiments/istina_online_read_load.py` | approval-gated, bounded-concurrency read-only online load generator |
| `config/istina_provenance_manifest.template.json` | intentionally invalid institutional provenance template |
| `config/istina_deployment_evidence.template.json` | intentionally invalid deployment evidence template |
| `config/istina_drift_monitor_verification.template.json` | intentionally invalid deployed-monitor proof template |
| `config/istina_audit_retention_verification.template.json` | intentionally invalid durable-audit proof template |
| `config/istina_paired_shadow_plan.template.json` | intentionally invalid prospective comparison plan |
| `config/istina_online_load_plan.template.json` | intentionally invalid institutional load approval plan |
| `docs/ISTINA_INSTITUTIONAL_HANDOFF.md` | exact private inputs, fixed thresholds, and release commands |
| `evidence/openalex_confirmation_default_current_20260719.json` | current-runtime public OpenAlex confirmation |
| `evidence/openalex_confirmation_rescue_ablation_current_20260719.json` | current-runtime in-domain OpenAlex rescue ablation |
| `evidence/openalex_10000works_default_current_20260719.json` | current-runtime 10,000-work OpenAlex cross-domain stress |
| `evidence/openalex_10000works_rescue_current_20260719.json` | paired large OpenAlex rescue negative-transfer ablation |
| `evidence/aminer_kdd18_test100_default_current_20260719.json` | complete current-runtime AMiner transfer stress |
| `evidence/aminer_kdd18_test100_rescue_current_20260719.json` | paired complete current-runtime AMiner rescue ablation |
| `evidence/aminer_kdd18_test100_first10_default_current_20260719.json` | bounded current-runtime AMiner transfer check |
| `evidence/aminer_kdd18_test100_first10_rescue_current_20260719.json` | bounded current-runtime AMiner rescue transfer check |
| `paper/istina_empirical_evidence_20260719.json` | 74-check, SHA-256-bound machine article package |
| `paper/ISTINA_EMPIRICAL_EVIDENCE_20260719.md` | article-ready tables, claims, limitations, and source traceability |

The current article package passes 74/74 integrity checks and has package ID
`54e243f53620386a001541b445f5bb3f527f8060a6383668994492b02c123490`.
Its independent release field remains false.

Raw mention-level advisor records and the private adjudication queue are
excluded from Git. Committed live evidence contains salted redacted identifiers
and paired outcomes; other evidence contains aggregates, input names, and
hashes only.

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
| Correct known merges | 0 / 5 | 27 / 38 |
| Merge precision | 0% (no predicted merges) | 100% |
| Known-author recall | 0.00% | 71.05% |
| Automatic accuracy | 94.22% | 95.88% |
| UNKNOWN rate | 5.08% | 3.33% |
| Wrong merges | 0 | 0 |
| Unseen false links | 0 | 0 |
| Local p95 latency | 12.96 ms | 1.34 ms |

The production default now disables the unique-local-surname initial heuristic.
The temporal audit showed that a historical “James A.” was wrongly merged to
the future “James Alexander”; local surname uniqueness is not global identity
evidence. The heuristic remains available only as an explicit ablation. This
change prevents observed wrong merges. With legacy fallback disabled, the
strict-temporal sample emits no automatic merge; the overlap-prone diagnostic
retains 100% observed merge precision at 71.05% known-author recall.

The earlier 1/5 and 28/38 framework counts were not an independent replacement
comparison: one decision used `legacy_service_validated_fallback`. The corrected
protocol disables legacy fallback while retaining the incumbent response only
as an observation. On the 38 diagnostic cases, the independent framework is
correct on 27 and the frozen legacy service on 24. Paired cells are: both
correct 17, framework only 10, legacy only 7, both incorrect 4. The exact
two-sided McNemar value is `p = 0.629058837890625`; the cleaned sample does not
establish a statistically significant advantage.

## Online shadow and operational validation

The strict temporal live smoke queried the real legacy endpoint for five known
mentions across four complete-paper requests:

- 5 runtime decisions and 0 service errors;
- framework fallback to the legacy service was disabled; the legacy result was
  observation-only, yielding 0/5 framework versus 3/5 legacy correct;
- 0 authorized commands and 0 write calls;
- audit redaction and the ephemeral durable hash chain passed, and the circuit
  remained closed;
- paper round-trip p95 was 15.206 seconds;
- smoke health passed, but release shadow verification failed because 5 is
  below the predeclared 500-mention minimum.

A current-service live run on 2026-07-20 used the cleaned per-author diagnostic
split and queried all 38 known mentions across 14 complete-paper requests. The
framework remained 27/38 correct, while the live incumbent changed from the
frozen 24/38 to 27/38. Current paired cells are both correct 20, framework only
7, legacy only 7, and both incorrect 4, giving exact two-sided McNemar `p = 1`.
The run had zero service errors, zero authorized commands, zero writes, a
verified ephemeral audit chain, no legacy-fallback framework stages, and
18.715-second paper-request p95. The article package preserves the frozen and
current incumbent results separately and machine-records the +3-correct drift.
This remains non-release evidence because the split overlaps papers and 38 is
below the 500-mention and 100-paper floors.

A follow-up availability check on 2026-07-20 initially found HTTP 503 responses
despite a reachable host and TCP port. Controlled direct/proxied replication
isolated the 503 to the workstation's inherited HTTP proxy: the same request
returned HTTP 200 and valid JSON when sent directly. The default project client
now disables ambient proxy inheritance, with explicit opt-in still available
for an approved proxy. A direct real-service diagnostic reproduced the
advisor's short-Cyrillic-family failure: the unguarded `Ма/Цзясин` request
returned the spurious ID `2508867`, which the conservative local layer rejected.
The query-only `ч` guard returned an exact name candidate, ID `621785695`, at
similarity 0.85, which the local layer accepted. This establishes current
read-only reachability and revalidates the guard behavior; it does not establish
release-scale availability or quality.

A separate user-authorized online load-path canary used four real requests,
concurrency two, and a 0.5 request/s start limit. All four completed, with zero
errors, zero writes, and 10.858-second p95. The artifact is machine-classified
as `bounded_non_release_canary`: user canaries are capped at 20 requests and can
never satisfy the institutional 1,000-request release check. The production
runner now requires the distinct `institutional_load_window` approval scope
and an independently verified immutable load plan before a threshold-passing
result can be release-eligible. The plan binds the dataset, exact code revision,
service endpoint hash, domain-separated man-id hash, request count, concurrency,
rate, timeout, change reference, approver role, and active window. Its exact
file hash is retained in the load result and the final deployment gate parses
the plan as a fifth attachment and repeats all checks. Both the online-load and
offline-performance runners now obtain the repository HEAD themselves and
reject a supplied revision that is merely 40-hex but not the executing code;
they also reject uncommitted source changes while allowing generated evidence,
paper, and run-output files.

The offline no-write operational run replayed all 753 temporal test mentions
(including rows without gold) for 18 iterations:

| Operational measure | Result |
|---|---:|
| Load operations | 13,554 |
| Throughput | 512.54 mentions/s |
| Local p95 | 6.67 ms |
| Deterministic-hash mismatches | 0 |
| Runtime safety/idempotency/redaction | passed |
| Durable fsync audit hash chain / restart verification | passed (8 records) |
| Circuit open, rejection, half-open, recovery | passed |
| Automatic rollback fault path | passed |
| UNKNOWN, merge-rate, stage, service-error drift alerts | passed |

An earlier uninstrumented run at commit `769363e` recorded 50.82 ms p95 and
failed the fixed 50 ms threshold; it remains preserved in Git history rather
than being silently discarded. The revised protocol freezes code revision and
trial ID, retains all 18 iteration p95 values, and still judges the overall
13,554-operation p95 against the unchanged 50 ms limit. Three sequential trials
on commit `fb866c3` all passed at 46.18, 46.17, and 42.24 ms. Profiling then
identified repeated Unicode decomposition and sorting of the same coauthor
names as the dominant local hot path. A bounded 65,536-entry normalization
cache preserves decisions while removing that duplicated work. On the frozen,
source-clean commit `167b7f7`, three new sequential trials passed at 7.29,
6.53, and 6.67 ms, totaling 40,662 operations with zero deterministic-hash
differences. Every artifact records successful repository-HEAD and clean-source
verification. The path-free aggregate requires every trial to pass; its
median/max are 6.67/7.29 ms, and the largest individual-iteration p95 is 8.34
ms. This restores a robust offline-load margin but is still not an online
end-to-end load test and does not prove that the drift monitor is connected to
production telemetry or paging. The audit test uses a temporary local file and
proves redaction, append durability, hash-chain integrity, and restart
verification for the single-process sink. The audit-retention evidence
generator now supports the documented multi-worker pattern by stream-verifying
one retained chain per worker, matching each head and record total to retained
fsync shadow telemetry, and emitting a path-free aggregate manifest root. The
55-check deployment validator rejects a hand-written `chain_verified`
assertion without this machine manifest. No qualifying retained production
chains exist yet, so this does not claim deployed audit retention.

The final repository regression command reports 251 passed tests and one
collection warning for a manual scenario class with a constructor. The ISTINA,
provenance, audit-integrity, and production-control suites are included.

## Public real-data external validation

The current runtime was rerun on the real OpenAlex/ORCID-blind confirmation
set. ORCID is used only as hidden identity gold and is absent from runtime
input. The exact dataset and metadata hashes match the original public-input
declaration. The zero-paper-overlap test contains 6,232 mentions: 3,680 known
and 2,552 unseen.

The production default obtains 100% observed merge precision, 71.93% known
recall, 78.90% automatic accuracy, 16.13% UNKNOWN, zero wrong merges, and 8.23
ms p95. The explicit in-domain rescue ablation keeps 100% observed precision
and zero wrong merges while changing recall to 72.93%, automatic accuracy to
79.49%, and UNKNOWN to 15.53%. These are the current article-package numbers;
the earlier six-seed aggregate in the superseded runtime artifact is retained
only for historical reproducibility and is not used as a current result.

The current runtime was also replayed on a larger, independently generated
OpenAlex sample with 10,000 complete works and 28,361 authorship rows spanning
five broad domains. The complete-paper split has 931 history mentions and
27,430 test mentions (552 known and 26,878 unseen), with zero paper overlap.
The default obtains 73.68% merge precision, 43.12% known recall, 88.83%
automatic accuracy, 10.84% UNKNOWN, 85 wrong merges, and 13.72 ms p95.
The paired rescue run raises recall to 48.37% but reduces precision to 48.90%
and increases wrong merges to 279. This result is a large public cross-domain
stress test, not a substitute for the required 10,000-mention ISTINA export.

The official AMiner KDD'18 archive was downloaded again and matched the
predeclared SHA-256. The complete current-runtime `test_100` replay finished at
the execution-window boundary and produced a valid compact artifact with 6,412
test mentions and zero paper overlap: 70.02% merge precision, 64.61% known
recall, 27.65% automatic accuracy, 60.51% UNKNOWN, 759 wrong merges, and 391.61
ms p95. Its quality counts independently reproduce the versioned historical
stress result, while the current artifact additionally binds the archive,
label, and publication-file hashes.

The previously long-running complete rescue process subsequently emitted a
valid compact artifact after 1,046.74 seconds. It uses the identical archive
and extracted-file hashes, all 100 name blocks, the same 6,412 test mentions,
and zero paper overlap. Rescue raises recall to 73.14%, but lowers precision to
63.03% and increases wrong merges from 759 to 1,177. The first-10-block bounded
comparison (679 test mentions) independently shows the same direction: recall
66.67% to 80.26%, precision 72.28% to 61.85%, and wrong merges 79 to 153. The
complete paired comparison therefore replaces the earlier timeout statement
and strengthens the negative-transfer finding; rescue remains disabled in the
cross-domain production default.

`evidence/runtime_validation_20260719.json` is now marked
`superseded_for_istina_claims`; its duplicate-leakage ISTINA result and old
OpenAlex and AMiner rows are machine-ineligible for current article or release
claims. The new paper package uses the current compact public-data replays and
binds every source table row to a file SHA-256.

## Machine gate

The release gate requires at least 10,000 test mentions, 1,000 known, 1,000
unseen, and 500 fair shadow cases as an absolute floor; merge precision at least 99.5%, recall at
least 95%, automatic accuracy at least 98%, UNKNOWN at most 2%, wrong-merge and
unseen-false-link rates at most 0.1%, and local p95 at most 50 ms. It also
requires cross-disciplinary adjudicated ISTINA gold, online no-write shadow,
online load, tested rollback, deployed drift monitoring, an independently
observed legacy comparator, and a pre-registered, adequately powered,
paper-cluster-aware paired comparison. Under the default
2-point-gain and 10%-discordance assumptions, the power calculation requires
a 1,960-mention base across at least 100 papers. The enforced collection target
is the base multiplied by the pre-registered cluster design effect, rounded up,
and cannot be below the registered or 500-mention floors.

Current result: **8 passed, 15 failed, 23 total; `release_ready: false`.**

Passed checks are wrong-merge rate, unseen false-link rate, local p95, runtime
safety contract, offline load, legacy-comparator independence,
rollback/circuit breaker, and drift-monitor fault testing.

Failed checks are total, known, unseen, and shadow sample sizes; merge
precision, known recall, automatic accuracy, UNKNOWN; significant absolute
legacy-shadow gain; paired significance; cross-disciplinary gold; 500-case
online shadow; online load; deployed drift monitoring; and the powered
cluster-aware paired analysis.

## Defensible article claims

1. A production-oriented, three-way author-disambiguation framework was
   implemented with deterministic audit traces, a redacted durable hash chain,
   idempotent commands, evidence-bound authorization, circuit breaking,
   automatic rollback, and drift monitoring.
2. A raw-export audit found and corrected a concrete leakage mechanism that
   materially changed the ISTINA result; the cleaned primary analysis is
   reported even though it is weaker.
3. On the available cleaned advisor sample, the independent framework makes no
observed wrong merge but also no strict-temporal automatic merge; the known-
author sample is only five and recall is not production-ready.
4. Strong in-domain OpenAlex behavior does not transfer to the official AMiner
   stress test, so universal superiority is not supported.
5. Strict-temporal online connectivity and no-write safety are demonstrated on
   five cases. A separate 38-case, 14-paper diagnostic reproduces the frozen
   27-versus-24 comparison live, but availability, latency at release scale,
   and deployed monitoring remain unproven.

It is not defensible to claim statistically significant superiority over the
legacy service on the cleaned ISTINA sample, universal author-disambiguation
superiority, or authorization for production writes.

## Reproduction

```powershell
python -m pytest -q -p no:cacheprovider

python evaluation/istina_gold_readiness.py --dataset <advisor-export.json> --service-result <frozen-service.json> --provenance-manifest evidence/istina_advisor_export_provenance_declaration_20260719.json --adjudication-output <private-queue.jsonl> --cleaned-output <private-cleaned.json> --output evidence/istina_gold_readiness_20260719.json

python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy temporal --train-through-year 2023 --service-result <frozen-service.json> --compact-output --output evidence/istina_temporal_runtime_replay_20260719.json

python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy per-author-holdout --service-result <frozen-service.json> --compact-output --output evidence/istina_holdout_runtime_replay_deduplicated_20260719.json

python experiments/openalex_runtime_replay.py --dataset <openalex-confirmation.jsonl> --metadata <openalex-metadata.json> --split-strategy orcid-author-holdout --compact-output --output evidence/openalex_confirmation_default_current_20260719.json

python experiments/openalex_runtime_replay.py --dataset <openalex-confirmation.jsonl> --metadata <openalex-metadata.json> --split-strategy orcid-author-holdout --enable-calibrated-candidate-rescue --compact-output --output evidence/openalex_confirmation_rescue_ablation_current_20260719.json

python experiments/openalex_runtime_replay.py --dataset <openalex-10000-work-sample.jsonl> --metadata <openalex-10000-work-metadata.json> --split-strategy article-holdout --compact-output --output evidence/openalex_10000works_default_current_20260719.json

python experiments/openalex_runtime_replay.py --dataset <openalex-10000-work-sample.jsonl> --metadata <openalex-10000-work-metadata.json> --split-strategy article-holdout --enable-calibrated-candidate-rescue --compact-output --output evidence/openalex_10000works_rescue_current_20260719.json

python experiments/aminer_kdd18_runtime_replay.py --data-root <aminer-data-global> --label-split test_100 --start-name 0 --max-names 10 --history-policy last-test --topk 20 --archive <na-data-kdd18.zip> --compact-output --output evidence/aminer_kdd18_test100_first10_default_current_20260719.json

python experiments/aminer_kdd18_runtime_replay.py --data-root <aminer-data-global> --label-split test_100 --start-name 0 --max-names 10 --history-policy last-test --topk 20 --archive <na-data-kdd18.zip> --enable-calibrated-candidate-rescue --compact-output --output evidence/aminer_kdd18_test100_first10_rescue_current_20260719.json

python experiments/aminer_kdd18_runtime_replay.py --data-root <aminer-data-global> --label-split test_100 --history-policy last-test --topk 20 --archive <na-data-kdd18.zip> --compact-output --output evidence/aminer_kdd18_test100_default_current_20260719.json

python experiments/aminer_kdd18_runtime_replay.py --data-root <aminer-data-global> --label-split test_100 --history-policy last-test --topk 20 --archive <na-data-kdd18.zip> --enable-calibrated-candidate-rescue --compact-output --output evidence/aminer_kdd18_test100_rescue_current_20260719.json

$env:ISTINA_AUDIT_SALT = <secret-manager-value>
python experiments/istina_live_shadow.py --dataset <advisor-export.json> --split-strategy temporal --train-through-year 2023 --limit 5 --audit-output <private-audit.jsonl> --output evidence/istina_live_shadow_smoke_20260719.json

python experiments/istina_live_shadow.py --dataset <advisor-export.json> --split-strategy per-author-holdout --limit 38 --code-revision <frozen-40-hex-revision> --output evidence/istina_live_shadow_diagnostic_20260720.json

python experiments/istina_operational_validation.py --dataset <advisor-export.json> --service-result <frozen-service.json> --live-shadow-evidence evidence/istina_live_shadow_smoke_20260719.json --split-strategy temporal --train-through-year 2023 --iterations 18 --code-revision <frozen-40-hex-revision> --performance-trial-id <trial-id> --tests-passed 251 --test-warnings 1 --output evidence/istina_operational_validation_trial1_20260720.json

python evaluation/istina_offline_performance_reproducibility.py --trial evidence/istina_operational_validation_trial1_20260720.json evidence/istina_operational_validation_trial2_20260720.json evidence/istina_operational_validation_trial3_20260720.json --expected-dataset <advisor-export.json> --expected-code-revision <frozen-40-hex-revision> --output evidence/istina_offline_performance_reproducibility_20260720.json

python experiments/istina_online_read_load.py --dataset <advisor-export.json> --requests 4 --concurrency 2 --max-rps 0.5 --man-id <approved-man-id> --code-revision <frozen-40-hex-revision> --approved-change-reference <user-task-reference> --approval-scope user_authorized_canary --acknowledge-read-only-load --output evidence/istina_online_read_load_canary_20260720.json

python evaluation/istina_evidence_bundle.py --operational-validation evidence/istina_operational_validation_20260719.json --gold-readiness evidence/istina_gold_readiness_20260719.json --live-shadow evidence/istina_live_shadow_smoke_20260719.json --output evidence/istina_release_evidence_bundle_20260719.json

python evaluation/production_gate.py --replay-result evidence/istina_operational_validation_20260719.json --evidence evidence/istina_release_evidence_bundle_20260719.json --output evidence/istina_production_gate_operational_20260719.json

python evaluation/istina_paper_package.py --temporal evidence/istina_temporal_runtime_replay_20260719.json --holdout evidence/istina_holdout_runtime_replay_deduplicated_20260719.json --operational evidence/istina_operational_validation_20260719.json --gold evidence/istina_gold_readiness_20260719.json --live evidence/istina_live_shadow_smoke_20260719.json --live-diagnostic evidence/istina_live_shadow_diagnostic_20260720.json --online-canary evidence/istina_online_read_load_canary_20260720.json --performance-reproducibility evidence/istina_offline_performance_reproducibility_20260720.json --bundle evidence/istina_release_evidence_bundle_20260719.json --gate evidence/istina_production_gate_operational_20260719.json --openalex-default evidence/openalex_confirmation_default_current_20260719.json --openalex-rescue evidence/openalex_confirmation_rescue_ablation_current_20260719.json --openalex-large-default evidence/openalex_10000works_default_current_20260719.json --openalex-large-rescue evidence/openalex_10000works_rescue_current_20260719.json --aminer-full-current evidence/aminer_kdd18_test100_default_current_20260719.json --aminer-full-rescue-current evidence/aminer_kdd18_test100_rescue_current_20260719.json --aminer-default-current evidence/aminer_kdd18_test100_first10_default_current_20260719.json --aminer-rescue-current evidence/aminer_kdd18_test100_first10_rescue_current_20260719.json --public-validation evidence/runtime_validation_20260719.json --output-json paper/istina_empirical_evidence_20260719.json --output-markdown paper/ISTINA_EMPIRICAL_EVIDENCE_20260719.md
```

## Evidence still required for replacement

Obtain an adjudicated, cross-disciplinary ISTINA export with at least 10,000
future test mentions, 1,000 verified identities already present in frozen
history, 1,000 genuine new identities, and a prospectively powered paired
comparison (500 is only the floor; the default assumptions produce a
1,960-case base before the registered cluster design effect).
The export must include discipline and sufficient affiliation/journal context,
and all unresolved label conflicts must be adjudicated. Its provenance manifest
must bind the exact file hashes, extraction time and method, label semantics,
independent audit, cross-discipline scope, and custodian approval. Then run the
registered number of cases through live no-write shadow across at least 100
papers, perform an online end-to-end load
test, deploy durable audit retention, and connect the tested drift monitor to
production telemetry and paging. Only a fully passing gate may authorize write
mode.
