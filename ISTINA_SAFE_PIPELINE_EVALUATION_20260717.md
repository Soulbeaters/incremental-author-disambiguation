# Safe ISTINA pipeline evaluation — 2026-07-17

## Scope

This report records reproducible results for the project-2 pipeline:

1. local Fellegi–Sunter three-way decision (`MERGE / NEW / UNKNOWN`);
2. conservative structured-name and coauthor repair for local `NEW` and
   `UNKNOWN` decisions;
3. the legacy ISTINA service only as a candidate source for remaining
   `UNKNOWN` cases, with local known-author validation before acceptance.

The advisor export is private and ignored by Git. No raw publication or author
data from that export is committed.

## Advisor ISTINA export

The supplied export contains 90 publications (10 per year, 2018–2026), 1,735
author mentions, 1,352 mentions with a gold ISTINA author ID, and 1,262 unique
gold authors. The deterministic per-author holdout uses one historical mention
for each of 88 repeated authors and evaluates 1,264 mentions: 90 mentions of
known authors and 1,174 mentions of previously unseen authors.

Command:

```powershell
python -X utf8 experiments\istina_export_temporal_evaluation.py `
  --dataset "C:\program 2 in 2025\istina test\chinese_articles_with_authors.json" `
  --split-strategy per-author-holdout --mode fs `
  --accept-threshold -0.5 --reject-threshold -4.0 `
  --min-accept-margin 1e-9 --require-context-for-low-name-accept `
  --enable-structured-repair --compare-service `
  --service-subset local-unknown --service-request-mode paper `
  --service-timeout 45 --service-sleep 15 `
  --output results\istina_safe_pipeline_structured_repair_context_required_20260717.json
```

| Stage | Correct merge | Wrong merge | Known-author recall | F1 | Auto accuracy | UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|
| Local FS | 69 | 0 | 76.67% | 86.79% | 97.31% | 1.50% |
| + structured/coauthor repair | 78 | 0 | 86.67% | 92.86% | 98.02% | 1.19% |
| + validated service fallback | 79 | 0 | 87.78% | 93.49% | 98.10% | 1.11% |

The structured repair attempted 1,195 local `NEW/UNKNOWN` records and accepted
only 9; all 9 matched gold. It recovered five false `NEW` decisions and four
`UNKNOWN` decisions. The final service fallback evaluated 15 remaining
`UNKNOWN` records in 10 whole-paper requests and accepted one; it was correct.

## Paired comparison with the legacy service

The legacy service was queried with the complete author list of each paper and
scored on exactly the same 90 known-author mentions. This avoids comparing a
forced legacy top-1 decision on one population with selective decisions on a
different population.

```powershell
python -X utf8 experiments\paired_istina_significance.py `
  --legacy-result results\istina_export_holdout_eval_shared_existing_paper_service90_20260717.json `
  --new-result results\istina_safe_pipeline_structured_repair_context_required_20260717.json `
  --output results\istina_paired_significance_new_vs_legacy_20260717.json
```

| Measure | Legacy ISTINA | New pipeline |
|---|---:|---:|
| Correct top-1 links | 35 / 90 | 79 / 90 |
| Accuracy | 38.89% | 87.78% |

The absolute gain is 48.89 percentage points. The paired table is 29 both
correct, 50 new-only correct, 6 legacy-only correct, and 5 both incorrect. The
exact two-sided McNemar/binomial p-value is `1.0182e-09`.

## Public-data regression and unseen-author safety

The unchanged public ORCID-blind FS benchmark has 699 evaluation mentions:
633 correct merges, 4 wrong merges, 99.37% merge precision, 90.56% known-author
recall, 94.76% F1, and 6.72% `UNKNOWN`. The core result is identical before and
after adding the isolated structured-repair module.

The public author-disjoint safety split holds out all mentions for 54 ORCID
authors. It contains 499 history mentions and 825 test mentions, including 265
mentions from completely unseen authors:

```powershell
python -X utf8 experiments\public_structured_repair_evaluation.py `
  --output results\structured_repair_public_orcid_blind_author_holdout_context_required_20260717.json
```

The public records contain no coauthor lists. Therefore the context-required
repair correctly abstains on every record: 0 accepted and 0 false links among
265 unseen-author mentions. This is a safety result, not evidence of positive
repair coverage; positive repair coverage is evaluated on the advisor export,
which contains paper-level coauthor context.

## Corrections to known legacy-service failure modes

- Short family names without patronymics receive a query-only guard, including
  the reproduced `Ма / Цзясин` case. Source data is never modified.
- The structured layer reads explicit family/given fields and has a fallback
  for ISTINA citation-style `Family I. O.` names.
- Equal names are not treated as equal identities. Every repair requires
  independent coauthor overlap and a unique known profile.
- Two people from the same paper cannot be collapsed by the repair layer.
- Historical profiles with incompatible family-name aliases are quarantined.
- Legacy service results are not trusted directly; only sufficiently similar
  IDs that are both locally known and present in the local FS top-k candidate
  set are eligible for final fallback acceptance.

## Current deployment status and limits

These results justify a shadow-deployment candidate and an article experiment,
not an immediate unmonitored replacement of the production service. The paired
known-author sample is only 90 and comes from a targeted publication export;
it is not a random sample of all ISTINA disciplines. The online service can
change independently, and load, latency, rollback, privacy, and drift monitoring
have not yet been validated. Production replacement still requires a larger
time-based ISTINA gold export and a shadow/canary run with explicit release
thresholds.
