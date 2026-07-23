# S2AND–RuZh residual result (2026-07-23)

## Decision

Retain this model as the first Project Two **public candidate** that passes the
registered joint non-regression gate against official S2AND.  It is a
preliminary algorithmic breakthrough on the frozen public temporal transfer
benchmark, not a SOTA claim and not an ISTINA blind-test result.

The method keeps official S2AND as the exact default.  A shallow residual
mixture-of-experts policy may replace an official decision only inside the
prespecified Russian/Chinese name stratum.  It learns two possible actions:
replace an official prediction with the Project Two specialist's candidate, or
veto a link to NIL.  The selected 2025+ policy used 19 replacements and no
vetoes.

## Leakage-controlled protocol

- Code revision: `715476a83b6e49bbe69403fa7784be13425f1c7d`
- 2023: 13,698 training queries; 4,301 target queries
- 2024: 16,083 validation queries; 5,448 target queries
- 2025+: 15,422 comparison queries; 5,574 target queries
- The Project Two specialist used five-fold out-of-fold 2023 predictions to
  train the residual action models.
- The threshold families were derived from 2023 scores.
- The two action thresholds were selected on 2024 only.
- The residual model was serialized, SHA-256 frozen and reloaded before the
  experiment code opened the 2025+ per-query S2AND outcomes.
- Non-target records are structurally routed to the exact official prediction.
- The advisor's ISTINA development or blind-test data was not used.

The validation target improved from 3,229 to 3,244 correct known links, reduced
wrong-known links from 75 to 74, and left new-author false links unchanged at
153.  It therefore passed the validation non-regression gate before the public
comparison was opened.

## Frozen 2025+ result

### Russian/Chinese target stratum

| Metric | Official S2AND | S2AND–RuZh residual | Change |
|---|---:|---:|---:|
| Known queries | 3,441 | 3,441 | — |
| New queries | 2,133 | 2,133 | — |
| Correct known links | 3,250 | 3,269 | **+19** |
| Wrong-known links | 112 | 109 | **−3** |
| New-author false links | 239 | 239 | **0** |
| Known recall | 0.944493 | 0.950015 | **+0.005522** |
| Known-prediction precision | 0.966686 | 0.967732 | **+0.001046** |
| New-author false-link rate | 0.112049 | 0.112049 | **0** |

All 19 changed predictions were correct: 16 rescued an official NIL decision
and three replaced an official wrong identity.  There were no candidate-only
errors.  The exact two-sided McNemar value for 19 improvements versus zero
regressions is `p = 3.814697265625e-06`.

### Overall linking

| Metric | Official S2AND | S2AND–RuZh residual | Change |
|---|---:|---:|---:|
| Correct known links | 8,835 | 8,854 | **+19** |
| Wrong-known links | 157 | 154 | **−3** |
| New-author false links | 265 | 265 | **0** |
| Known recall | 0.962943 | 0.965014 | **+0.002071** |
| Known-prediction precision | 0.982540 | 0.982904 | **+0.000364** |
| Accepted-link precision | 0.954413 | 0.954815 | **+0.000402** |
| New-author false-link rate | 0.042420 | 0.042420 | **0** |

The policy returned the exact official output for 15,403/15,422 queries,
including all 9,848 non-target queries.  The machine promotion gate reports:

- correct-known delta `+19`;
- wrong-known delta `−3`;
- new false-link delta `0`;
- non-target disagreements `0`;
- gate result `passed`.

## What this proves—and what it does not

This result proves that the residual architecture can start from the official
S2AND operating point and make a small, statistically nontrivial linking
improvement without shifting errors to another registered outcome on this
public temporal benchmark.  That is materially stronger than the previous
standalone Project Two models, which gained precision only by losing recall.

It does not establish global SOTA:

1. the Crossref–ORCID public comparison had already influenced earlier Project
   Two development decisions, so it is not a pristine independent benchmark;
2. the target detector is dominated by Pinyin/common-Chinese-name shapes and
   contains few genuine Cyrillic/Palladius cases;
3. only one public corpus and one temporal split support the current result;
4. exact S2AND new-query cluster tokens were not retained in the anonymous
   per-query checkpoint, so the report makes no exact B3/Pairwise superiority
   claim; and
5. no independently sealed ISTINA blind test has been run.

The correct next step is replication on an independent Chinese-rich benchmark
such as WhoIsWho and adaptation on a labelled ISTINA development set.  Only
after code, feature schema, models and thresholds are refrozen may the
advisor-held ISTINA blind test be evaluated once.

## Reproducibility

- Local aggregate:
  `runs/ruzh_s2and_residual_20260723_v1/aggregate_result.json`
- Aggregate SHA-256:
  `C87CF212BADEF0375D47FF3FFD957EFC26792F85110DE570A8F63B49D591BEBD`
- Frozen residual model SHA-256:
  `FC29EA7A8A5123D5D491CFC0CE0A7999EE3A76BD807F71D5FBA7A1ABE3F4E541`
- Compact record-free evidence:
  `evidence/ruzh_s2and_residual_20260723.json`
- Full test suite before the formal run: 375 passed.
