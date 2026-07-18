# ISTINA author-disambiguation status — 2026-07-18

## Current conclusion

The branch is a reproducible high-precision candidate and is suitable for
offline evaluation and ISTINA shadow integration. It is **not yet approved as
a write-enabled replacement**. The machine release gate returns
`release_ready: false` because public cold-start recall, automatic accuracy,
UNKNOWN rate, unseen-author false links, live shadow volume, and operational
evidence do not yet meet the predeclared production criteria.

## What is implemented

- formal side-effect-free `IstinaDisambiguationPipeline`;
- Fellegi–Sunter three-way `MERGE / NEW / UNKNOWN` base decisions;
- structured family/given-name repair with same-paper exclusion;
- coauthor and exact-affiliation evidence for abbreviated names;
- multilingual common-surname risk guards and ambiguity blocking;
- history conflict quarantine and external ISTINA ID mapping;
- one request per paper to the advisor-provided legacy service;
- query-only short-family repair: a missing patronymic is temporarily filled
  with `ч` for the legacy request and is never written to source data;
- validation of legacy `result_id` against known local candidates instead of
  trusting a returned ID blindly;
- privacy-redacted deterministic decision traces;
- reproducible OpenAlex/ORCID builders, field/domain slices, latency metrics,
  McNemar comparison, and a machine-readable release gate.

## Advisor ISTINA export

Source: 90 publications selected from 2018 onward by the advisor. The file
contains 1,735 authorships, of which 1,352 carry usable author IDs. The
per-author holdout contains 88 history mentions and 1,264 test mentions:
90 known-author cases and 1,174 unseen-author cases.

| Metric | Current framework | Legacy ISTINA service |
|---|---:|---:|
| Correct known-author decisions | 86 / 90 | 35 / 90 |
| Existing-author recall | 95.56% | 38.89% |
| Merge precision | 100% | — |
| Wrong merges | 0 | — |
| UNKNOWN rate over all test mentions | 1.03% | — |
| Automatic accuracy | 98.66% | — |
| Local p95 latency | 3.11 ms | — |

The paired comparison has McNemar exact two-sided
`p = 1.6979681549678105e-12`. The result includes a concrete correction of the
legacy short-surname/empty-patronymic failure mode and rejects inconsistent
legacy IDs when local history and returned names disagree.

## Public ORCID-blind results

ORCID is used only as hidden identity gold. It is never passed to the runtime.
Every one-paper split has zero publication overlap.

| Seed | Authors | Test mentions | Precision | Existing recall | UNKNOWN | Wrong merge rate |
|---:|---:|---:|---:|---:|---:|---:|
| 20260719 | 2,500 | 10,380 | 100% | 79.57% | 13.83% | 0% |
| 20260720 | 2,500 | 10,370 | 100% | 80.54% | 12.84% | 0% |
| 20260721 confirmation | 1,500 | 6,232 | 99.84% | 82.53% | 10.32% | 0.080% |

The confirmation set contains five false links among 2,552 unseen-author
mentions (0.196%), above the release requirement of 0.1%. Two- and
three-history-paper experiments remained near 83% recall and 13–14% UNKNOWN;
they did not remove the public cold-start limitation.

## Predeclared production gate

Key requirements include at least 10,000 test mentions, precision at least
99.5%, existing recall at least 95%, automatic accuracy at least 98%, UNKNOWN
at most 2%, wrong merges at most 0.1%, unseen-author false links at most 0.1%,
and p95 local latency at most 50 ms. Live shadow comparison (at least 500
mentions), load testing, rollback, and drift monitoring are also mandatory.

The 20260721 confirmation passes precision, overall wrong-merge, existing/new
sample size, and latency checks. It fails total sample size for that individual
run, recall, automatic accuracy, UNKNOWN, unseen false links, legacy shadow
volume, and operational checks. No production claim should be made until those
failures are resolved.

## Next research step

Train an interpretable calibrated candidate-risk model on the 20260718–20
ORCID-labelled datasets and evaluate it on author-disjoint data. It should run
only after the deterministic risk guards, rescue selected UNKNOWN decisions,
and retain the three-way output. A GNN is optional only after this calibrated
baseline; graph complexity is not justified unless it gives a statistically
significant improvement on the same candidate set and release criteria.
