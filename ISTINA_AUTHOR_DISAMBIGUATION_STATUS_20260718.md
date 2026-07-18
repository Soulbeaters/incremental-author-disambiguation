# ISTINA author-disambiguation evidence — 2026-07-18

## Release verdict

This branch is a reproducible, high-precision **shadow/candidate release** and
is suitable for an article comparison. It is **not yet authorized as a
write-enabled replacement for the ISTINA service**. The machine release gate
returns `release_ready: false`: the advisor export is too small for the
predeclared ISTINA sample thresholds, and online shadow, load, rollback, and
drift-monitoring evidence is still absent. Public open-world data also does not
meet the deliberately strict recall and UNKNOWN targets.

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

An interpretable frozen logistic candidate-rescue model is retained for
reproducible ablation only. It is **disabled by default** because enabling it
did not remain safe across the independent public and ISTINA domains.

## Advisor ISTINA export and legacy comparison

The advisor export contains 90 publications selected from 2018 onward and
1,735 authorships; 1,352 authorships have usable author IDs. A deterministic
per-author holdout uses 88 history mentions and 1,264 test mentions: 90 known
authors and 1,174 unseen authors. Source IDs are hidden from runtime and used
only as gold labels. The old-service results were frozen before the final run,
so both methods are compared on the same 90 known-author mentions.

| Metric | New framework | Existing ISTINA service |
|---|---:|---:|
| Correct known-author decisions | 86 / 90 | 35 / 90 |
| Known-author accuracy/recall | 95.56% | 38.89% |
| Merge precision | 100% | not derivable from this known-only shadow |
| Wrong merges | 0 | not separately reported by the service |
| Automatic accuracy, all 1,264 mentions | 98.58% | not comparable |
| UNKNOWN rate, all 1,264 mentions | 1.11% | not exposed |
| Local p95 latency | 11.82 ms | network service latency not frozen |

Paired outcomes are: both correct 31, new only correct 55, legacy only correct
4, both incorrect 0. The absolute known-author gain is 56.67 percentage points;
the exact two-sided McNemar result is `p = 1.6979681549678105e-12`.

This run fixes the demonstrated short-family/empty-patronymic failure mode and
rejects inconsistent service IDs when returned names and local history do not
support the same identity. The result is statistically strong but the sample
is still only 90 shared known-author cases.

## Six independent OpenAlex/ORCID-blind runs

Data were collected from the OpenAlex API. ORCID defines hidden identity gold
and is removed from runtime input. The split assigns known and unseen authors
deterministically, gives each known author one complete history paper, and has
zero publication overlap. Seeds are experiment identifiers, not collection
dates.

| Seed | Authors | Test | Known | New | Precision | Known recall | Auto accuracy | UNKNOWN | Unseen false links | p95 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20260719 | 2,500 | 10,380 | 6,247 | 4,133 | 100.000% | 79.43% | 81.47% | 15.66% | 0 / 4,133 | 24.72 |
| 20260720 | 2,500 | 10,370 | 6,386 | 3,984 | 100.000% | 80.49% | 82.36% | 14.92% | 0 / 3,984 | 18.94 |
| 20260721 | 1,500 | 6,232 | 3,680 | 2,552 | 100.000% | 82.07% | 84.88% | 12.45% | 0 / 2,552 | 19.76 |
| 20260722 | 1,500 | 6,221 | 3,825 | 2,396 | 99.968% | 81.75% | 83.31% | 13.78% | 1 / 2,396 | 21.17 |
| 20260723 | 1,500 | 6,210 | 3,781 | 2,429 | 99.968% | 81.72% | 84.77% | 12.45% | 1 / 2,429 | 11.19 |
| 20260724 | 1,000 | 4,110 | 2,618 | 1,492 | 99.953% | 81.86% | 83.80% | 12.14% | 1 / 1,492 | 11.73 |
| **Aggregate** | **10,500** | **43,523** | **26,537** | **16,986** | **99.986%** | **80.95%** | **83.13%** | **13.96%** | **3 / 16,986 (0.0177%)** | — |

Aggregate counts are 21,482 correct merges, 3 wrong merges, 14,697 correct
NEW decisions, 1,264 false-NEW known authors, and 6,077 UNKNOWN decisions.
The three remaining wrong merges are information-poor initial-only names; the
system intentionally does not hide this open-world limitation.

## Production gate

The predeclared gate requires at least 10,000 test mentions, 1,000 known and
1,000 unseen mentions, 500 shared legacy-shadow mentions, merge precision at
least 99.5%, known recall at least 95%, automatic accuracy at least 98%,
UNKNOWN at most 2%, wrong merges and unseen false links each at most 0.1%, and
local p95 latency at most 50 ms. Cross-domain ISTINA gold, online no-write
shadowing, load testing, tested rollback/circuit breaker, and drift monitoring
are also mandatory.

- Public 20260719 gate: 7/18 checks pass; recall, automatic accuracy, UNKNOWN,
  shadow comparison, and operations fail.
- Advisor ISTINA gate: 10/18 checks pass, including every measured quality,
  comparison, significance, and latency threshold. It fails the total, known,
  and shadow sample-size thresholds plus the five operational requirements.

Therefore the defensible article claim is: **the framework significantly
improves the existing ISTINA service on the available advisor-labelled shadow
set while preserving high precision, auditability, and explicit risk control**.
It is not defensible yet to claim universal superiority or production
replacement.

## Reproduction

```powershell
python -B -m unittest discover -s tests -v
python experiments/openalex_runtime_replay.py --dataset <mentions.jsonl> --metadata <metadata.json> --split-strategy orcid-author-holdout --history-papers-per-known-author 1 --topk 20 --output <result.json>
python experiments/istina_runtime_replay.py --dataset <advisor-export.json> --split-strategy per-author-holdout --service-result <frozen-service-result.json> --output <result.json>
python -m evaluation.production_gate --replay-result <result.json> --output <gate.json>
```

Private advisor data and frozen service responses are intentionally not
committed. Public datasets can be rebuilt with
`data/build_openalex_orcid_benchmark.py`; experiment metadata, source URLs,
collector parameters, and SHA-256 checksums must be retained with each build.

## Minimum evidence still required for replacement

Obtain at least 1,000 verified repeated-author ISTINA mentions and at least 500
of those evaluated by both systems, covering multiple disciplines, common
names, initials, Cyrillic/Latin/CJK variants, changed affiliations, and genuine
new authors. Then run the same frozen protocol in no-write shadow mode and add
load, rollback, and drift evidence. Only a fully passing machine gate can
authorize write-enabled integration.
