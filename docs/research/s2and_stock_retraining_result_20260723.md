# Stock-S2AND public retraining control result

Date: 2026-07-23

## Status and claim boundary

The unchanged stock-S2AND control completed.  This is a public development
experiment, not an ISTINA blind test and not a Project Two method
contribution.  It measures ordinary in-domain retraining and parameter
adaptation.

Training used official S2AND `0.51.1` at revision
`cb99b97c23a7c1bdbcb98cfe68abc6fec060c402`.  Project Two training revision was
`57aa4d21c5e1d48dbd9a6551a45e57ea617739c5`; the final model SHA-256 is
`f9244e2a3c318887f4755fe3d949b6cec1921551c84fc0c0084b430c33784222`.

The deterministic 30% complete-name-block materialization contains 14,334
train, 4,272 validation and 4,935 2024 development-test authorships.  It
provides 155,104/12,620/19,888 unique within-block pair opportunities, from
which S2AND draws 100,000/10,000/10,000 pairs.  ORCID is hashed cluster
supervision only and is absent from all features.

## Training result

| Diagnostic | Validation 2023 | Development test 2024 |
|---|---:|---:|
| Pair ROC AUC | 0.998473 | 0.999074 |
| Average precision | 0.998151 | 0.998305 |
| Brier score | 0.006908 | 0.004208 |
| Pairs | 10,000 | 10,000 |

The selected average-linkage threshold is `eps=0.4466266107058334`.
Training took 389.9 seconds and the measured peak resident working set was
7,635,906,560 bytes.  The fitted pair classifier is a shallow adapted
LightGBM (`max_depth=2`, `n_estimators=1387`); these fitted values are control
parameters, not novelty.

## Frozen 2025--2026 incremental comparison

Both models see the same 44,879 history authorships, 15,422 query authorships,
8,027 name blocks, 9,175 known-author queries and 6,247 new-author queries.
Both use the official exact Python incremental path and the identical
candidate/seed contract.

| Metric | Official S2AND v1.21 | Stock retrained | Delta |
|---|---:|---:|---:|
| Correct known | 8,835 | 8,795 | -40 |
| Known recall | 0.962943 | 0.958583 | -0.004360 |
| Known prediction precision | 0.982540 | 0.982901 | +0.000361 |
| Wrong-known events | 157 | 153 | -4 |
| New false-link events | 265 | 188 | -77 |
| New false-link rate | 0.042420 | 0.030094 | -0.012326 |
| Accepted-link precision | 0.954413 | 0.962675 | +0.008262 |
| B³ F1 | 0.990210 | 0.991560 | +0.001350 |
| Pairwise F1 | 0.973474 | 0.968533 | -0.004940 |

The stock model's 95% Wilson intervals are:

- known recall: 0.954310--0.962472;
- known prediction precision: 0.980000--0.985387;
- new-author false-link rate: 0.026138--0.034628;
- accepted-link precision: 0.958590--0.966372.

Scientific counts, linking metrics and clustering metrics were identical in
two complete executions.  The final evidence run used Project Two revision
`700b772de79e27b3523b78bb4b078024e68c490b`, result run signature
`236edfda0586d1d4b3c52f12a54dc6cb6c30d4e6b371013f44f326159b508ace`,
and measured 4,948,807,680 bytes peak RSS.  Its aggregate metric SHA-256
(including runtime fields) is
`fb30df2625417bb2157de6e4825d91b18df2bb3729c32fdb574055c736783852`.

## Interpretation

In-domain stock retraining improves the low-risk side of the frontier:
77 fewer new-author false links and higher accepted-link precision.  It loses
40 correct known links, and its pairwise clustering F1 is lower.  The small B³
gain therefore does not establish overall superiority over official S2AND.

This control rejects two weak paper claims:

1. hyperparameter tuning alone is not a Project Two method contribution; and
2. high pair-classification AUC does not imply a superior incremental
   disambiguation pipeline.

The next method must compare against both the frozen official bundle and this
adapted stock model.  A useful target is an `S2AND-RuZh-Open` decision layer
that preserves stock-S2AND's high known-author recall while reducing
new-author false links under a separately certified risk bound.  Russian,
Chinese and Palladius-specific gains still require verified target-domain
labels because the public corpus has almost no relevant cross-script pairs.
