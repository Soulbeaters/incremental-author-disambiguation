# ISTINA author-disambiguation evidence — 2026-07-18

## Release verdict

This branch is a reproducible, high-precision **shadow/candidate release** and
is suitable for an article comparison. It is **not yet authorized as a
write-enabled replacement for the ISTINA service**. The machine release gate
returns `release_ready: false`: the advisor export is too small for the
predeclared ISTINA sample thresholds. The production safety runtime, offline
load replay, circuit breaker, automatic rollback, and drift fault injection are
now verified. A bounded live no-write shadow was attempted and failed closed
after three service timeouts, so cross-discipline ISTINA gold, a reliable
500-mention live shadow, online load testing, and deployed drift monitoring are
still absent. Public open-world data also does not meet the deliberately strict
recall and UNKNOWN targets.

## Final default runtime

The default pipeline contains:

- multilingual Unicode/diacritic-aware candidate blocking without changing
stored source names;
- structured family/given-name, compound-name token, and conservative
  initials repair;
- normalized order-insensitive coauthor evidence;
- Fellegi–Sunter scoring with `MERGE / NEW / UNKNOWN` decisions;
- dense/common-name guards that require independent coauthor, journal, ORCID,
  or affiliation evidence (`affiliation similarity >= 0.40`);
- quarantine of conflicting history identities and same-paper leakage guards;
- one legacy-service query per paper, including the query-only short-family
  workaround for a missing patronymic;
- validation of returned legacy IDs against local candidates;
- top-20 redacted, deterministic audit traces with score components and raw
  comparisons.

## Production safety envelope — 2026-07-19

`integrations.istina_production_runtime` now wraps the statistical runtime with
a side-effect-free production boundary:

- `shadow`, `candidate`, and `write` modes are explicit; the default is
  `shadow`;
- write mode cannot start without a non-expired production authorization whose
  commit SHA and SHA-256 evidence hash match the running code and whose evidence
  JSON itself reports `release_ready: true`;
- the runtime emits deterministic, idempotent downstream commands and does not
  write to ISTINA directly;
- a closed/open/half-open circuit breaker isolates the legacy service;
- any service error or rolling decision-drift alert automatically rolls an
  intended write deployment back to `shadow` before an authorized command is
  emitted;
- rolling checks cover UNKNOWN and merge-rate shifts, stage-distribution total
  variation, service errors, candidate truncation, and p95 latency;
- production audit events hash names and publication identifiers and never
  authorize writes in shadow/candidate mode.

The no-write operational replay used the real advisor export and the frozen
90-case service comparison. Eight repeats processed 10,112 operations over the
same 1,264 genuine test mentions; repeated operations are explicitly **not**
counted as additional gold. It achieved 610.30 mentions/second, local p95
8.77 ms, and 0 deterministic-hash mismatches. The safety contract, circuit
breaker recovery, automatic rollback, and injected drift alerts all passed.
The final repository regression suite reports 157 passed tests and 27 warnings.

A preliminary bounded connectivity check returned results for five known
authors, but the final strict rerun (after strengthening the audit-redaction
assertion) timed out on all three complete-paper requests. The final evidence
therefore records five service-error decisions, zero authorized writes,
paper-request p95 20.72 seconds, and an open circuit after the third failure.
Audit redaction still passed and the local runtime continued fail-closed. This
demonstrates the rollback path, but **does not verify online shadow
availability**. Compact evidence is committed in:

- `evidence/istina_operational_validation_20260719.json`;
- `evidence/istina_live_shadow_smoke_20260719.json`;
- `evidence/istina_production_gate_operational_20260719.json`.

An interpretable L2-logistic candidate-rescue model is retained for explicit
OpenAlex ablation, but is disabled in the production default because it did not
transfer safely to the official AMiner benchmark. It was fitted on seed
20260719 and its threshold was selected once on seed 20260720 under a 0.1%
unseen-author false-link budget. The offline Newton fitting script reproduces
every runtime mean, scale, coefficient, and threshold with zero numeric delta;
runtime inference remains standard-library only. Common-name guards use
official aggregate surname statistics, including
the [U.S. Census surname files](https://www.census.gov/data/developers/data-sets/surnames.html)
and the [UK government 2026 top-five table](https://www.gov.uk/csv-preview/69cb9f30a60a12ca3913c603/sia-4b-top-5-last-names.csv).

## Advisor ISTINA export and legacy comparison

The advisor export contains 90 publications selected from 2018 onward and
1,735 authorships; 1,352 authorships have usable author IDs. A deterministic
per-author holdout uses 88 history mentions and 1,264 test mentions: 90 known
authors and 1,174 unseen authors. Source IDs are hidden from runtime and used
only as gold labels. The old-service results were frozen before the final run,
so both methods are compared on the same 90 known-author mentions.

| Metric | New framework | Existing ISTINA service |
|---|---:|---:|
| Correct known-author decisions | 85 / 90 | 35 / 90 |
| Known-author accuracy/recall | 94.44% | 38.89% |
| Merge precision | 100% | not derivable from this known-only shadow |
| Wrong merges | 0 | not separately reported by the service |
| Automatic accuracy, all 1,264 mentions | 98.50% | not comparable |
| UNKNOWN rate, all 1,264 mentions | 1.11% | not exposed |
| Local p95 latency | 7.53 ms | network service latency not frozen |

Paired outcomes are: both correct 31, new only correct 54, legacy only correct
4, both incorrect 1. The raw-label absolute known-author gain is 55.56
percentage points; the exact two-sided McNemar result is
`p = 3.1699504132731704e-12`.

This run fixes the demonstrated short-family/empty-patronymic failure mode and
rejects inconsistent service IDs when returned names and local history do not
support the same identity. A label audit found four clearly inconsistent test
mentions: ID `1078148` maps history `Peng Peng` to test `Bi K.` and `Dawson
Amanda Caroline`; ID `11121362` maps `Mark L.` to `Kouli Omar`; and ID
`1618329` maps `Kustov A.L.` to `Кустов Л.М.`. These are reported as suspicious
gold and remain counted as errors in the primary table. The fifth miss,
`Khan A.` versus `Khan Amir`, is intentionally not auto-merged without
independent context after the official high-frequency-surname guard. The
result is statistically strong, but the sample is still only 90 shared cases
and the suspected labels require advisor verification.

## Six OpenAlex/ORCID-blind calibrated-rescue ablations

Data were collected from the OpenAlex API. ORCID defines hidden identity gold
and is removed from runtime input. The split assigns known and unseen authors
deterministically, gives each known author one complete history paper, and has
zero publication overlap. Seed 20260719 is training, 20260720 is threshold
validation, and 20260721–20260724 are untouched confirmation runs. Seeds are
experiment identifiers, not collection dates.

The table below is the explicit in-domain calibrated-rescue ablation, not the
cross-domain production default. The rescue is disabled by default after the
official AMiner test showed that it does not transfer safely. On the untouched
20260721 confirmation set, the deterministic default without rescue has 100%
merge precision, 81.98% known-author recall, 84.84% automatic accuracy, and
12.48% UNKNOWN; the corresponding rescue ablation is the 20260721 row below.

| Seed | Authors | Test | Known | New | Precision | Known recall | Auto accuracy | UNKNOWN | Unseen false links | p95 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20260719 train | 2,500 | 10,380 | 6,247 | 4,133 | 100.000% | 80.04% | 81.84% | 15.22% | 0 / 4,133 | 20.11 |
| 20260720 threshold | 2,500 | 10,370 | 6,386 | 3,984 | 100.000% | 81.30% | 82.86% | 14.41% | 0 / 3,984 | 14.66 |
| 20260721 confirmation | 1,500 | 6,232 | 3,680 | 2,552 | 100.000% | 82.80% | 85.32% | 12.00% | 0 / 2,552 | 11.10 |
| 20260722 confirmation | 1,500 | 6,221 | 3,825 | 2,396 | 99.968% | 82.41% | 83.72% | 13.37% | 1 / 2,396 | 11.72 |
| 20260723 confirmation | 1,500 | 6,210 | 3,781 | 2,429 | 99.968% | 82.76% | 85.39% | 11.82% | 1 / 2,429 | 7.53 |
| 20260724 confirmation | 1,000 | 4,110 | 2,618 | 1,492 | 99.954% | 82.58% | 84.26% | 11.68% | 1 / 1,492 | 7.94 |
| **Aggregate** | **10,500** | **43,523** | **26,537** | **16,986** | **99.986%** | **81.70%** | **83.59%** | **13.48%** | **3 / 16,986 (0.0177%)** | — |

Aggregate counts are 21,682 correct merges, 3 wrong merges, 14,697 correct
NEW decisions, 1,273 false-NEW known authors, and 5,868 UNKNOWN decisions.
Relative to commit `1618075`, v2 adds 200 correct merges and removes 209
UNKNOWN decisions without adding a wrong merge; recall rises by 0.75 percentage
points and automatic accuracy by 0.46 points.
The three remaining wrong merges are information-poor initial-only names; the
system intentionally does not hide this open-world limitation.

## Official AMiner KDD'18 stress test

The public archive is downloaded from the official AMiner URL and is not
redistributed. Its SHA-256 is
`d3912ea052afed43eeb401788312ab936055b02c2a52fd790c5c69e13db9defd`.
All 35,129 labelled mentions in `test_100` were checked against the stated
paper author position and entity ID before evaluation. A complete-paper
last-test split produces 28,717 history mentions and 6,412 test mentions with
zero publication overlap; 2,744 test authorships belong to identities present
in history and 3,668 belong to unseen identities.

| Metric | Deterministic default |
|---|---:|
| Correct known-author merges | 1,773 / 2,744 |
| Merge precision | 70.02% |
| Known-author recall | 64.61% |
| Existing-author F1 | 67.21% |
| Wrong merges | 759 / 6,412 (11.84%) |
| UNKNOWN | 3,880 / 6,412 (60.51%) |
| Automatically accepted NEW | 0 |
| Automatic accuracy | 27.65% |
| Local p95 latency | 624.70 ms |
| Candidate pool truncated | 3,326 / 6,412 (51.87%) |
| Average complete / scored candidates | 111.21 / 78.94 |

This is an intentionally difficult same-name, open-world stress test. It
falsifies any claim that the current generic runtime is universally
production-ready. A learned bibliographic candidate retriever and a stricter
context guard were also tested on all 6,412 mentions; they reduced wrong merges
but lowered F1 and increased UNKNOWN, so they were removed from the final
runtime. The retained engineering improvement is reproducibility: external
author IDs are stable, and bounded affiliation/journal blocking keys are sorted
before truncation. Three independent processes then produced the same candidate
count and SHA-256 digest on the dense 554-mention diagnostic subset.

## Production gate

The predeclared gate requires at least 10,000 test mentions, 1,000 known and
1,000 unseen mentions, 500 shared legacy-shadow mentions, merge precision at
least 99.5%, known recall at least 95%, automatic accuracy at least 98%,
UNKNOWN at most 2%, wrong merges and unseen false links each at most 0.1%, and
local p95 latency at most 50 ms. Cross-domain ISTINA gold, online no-write
shadowing, load testing, tested rollback/circuit breaker, and drift monitoring
are also mandatory.

- Public 20260719 gate: 7/18 checks pass; recall, automatic accuracy, UNKNOWN,
  shadow comparison, and operations fail. This is the in-domain calibrated
  rescue ablation, not the production default.
- Untouched OpenAlex 20260721 deterministic-default gate: 6/18 checks pass;
  merge precision, wrong-link safety, sample composition, and latency pass,
  while recall, automatic accuracy, UNKNOWN, shadow comparison, and operations
  fail.
- Advisor ISTINA operational gate: 13/21 checks pass, but `release_ready`
  remains `false`. Runtime safety, offline load, rollback/circuit-breaker, and
  drift fault testing pass. The eight remaining failures are total mentions
  (1,264 / 10,000), existing mentions (90 / 1,000), shared shadow mentions
  (90 / 500), raw known-author recall (94.44% / 95%), cross-discipline ISTINA
  gold, reliable online shadow, online load testing, and deployed drift
  monitoring.
- Official AMiner `test_100` deterministic-default gate: 2/18 checks pass.
  Only the existing- and unseen-author sample counts pass; precision, recall,
  automatic accuracy, UNKNOWN, false links, latency, comparison, and operations
  fail.

Therefore the defensible article claim is: **the framework significantly
improves the existing ISTINA service on the available advisor-labelled shadow
set while preserving high precision, auditability, and explicit risk control**.
It is not defensible yet to claim universal superiority or production
replacement.

## Reproduction

```powershell
python -B -m unittest discover -s tests -v
python experiments/openalex_runtime_replay.py --dataset <mentions.jsonl> --metadata <metadata.json> --split-strategy orcid-author-holdout --history-papers-per-known-author 1 --topk 20 --enable-calibrated-candidate-rescue --output <ablation-result.json>
python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy per-author-holdout --service-result <frozen-service-result.json> --output <result.json>
python experiments/aminer_kdd18_runtime_replay.py --data-root <na-data-kdd18/data/global> --label-split test_100 --archive <na-data-kdd18.zip> --output <result.json>
python experiments/train_calibrated_candidate_model.py --train-result <seed19-risk-baseline.json> --validation-result <seed20-risk-baseline.json> --topk 20 --verify-runtime-model --output <model-artifact.json>
python experiments/istina_live_shadow.py --dataset <advisor-export.json> --limit 5 --output <live-shadow.json>
python experiments/istina_operational_validation.py --dataset <advisor-export.json> --service-result <frozen-service-result.json> --live-shadow-evidence <live-shadow.json> --iterations 8 --output <operational-evidence.json>
python -m evaluation.production_gate --replay-result <result.json> --output <gate.json>
```

Private advisor data and frozen service responses are intentionally not
committed. Public datasets can be rebuilt with
`data/build_openalex_orcid_benchmark.py`; experiment metadata, source URLs,
collector parameters, and SHA-256 checksums must be retained with each build.
The compact machine-readable validation record is committed as
`evidence/runtime_validation_20260719.json`; full per-mention replay files stay
outside Git because they contain private records or large generated data.

## Minimum evidence still required for replacement

Obtain at least 10,000 cross-disciplinary ISTINA test mentions, including at
least 1,000 verified repeated-author mentions and at least 500 cases evaluated
by both systems. The new gold must cover multiple disciplines, common names,
initials, Cyrillic/Latin/CJK variants, changed affiliations, and genuine new
authors. Run at least 500 of those cases through the live no-write runtime,
perform online end-to-end load testing, and deploy the tested drift monitor.
The available export cannot supply these missing identities: it contains only
88 repeated gold authors and 90 known-author test mentions. Only a fully passing
machine gate and matching evidence-bound authorization can enable write mode.
