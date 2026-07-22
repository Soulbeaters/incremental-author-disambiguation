# Grouped ranker plus NIL gate — development result, 2026-07-22

## Question

This experiment stops coefficient/threshold-only iteration and changes the
model structure.  Candidate retrieval is frozen.  A query-group LambdaMART
model first ranks the existing candidates; a separate cost-sensitive
LightGBM model then accepts the top candidate or emits `NIL/UNKNOWN`.
The NIL model is trained from five-fold out-of-paper ranker predictions, not
from the ranker's own in-sample scores.

This architecture follows the separation between candidate matching and NIL
classification in CONNA and the group-aware tree baselines used by S2AND and
WhoIsWho.  It is an offline ablation, not a production dependency.

## Data role

The source is the same 120,815-authorship real Crossref--ORCID development
export.  All 2022 and 2023+ labels were already opened by earlier experiments
and are development-only.  The fifth 2022 paper bucket is marked
`opened_development`; the code forces `promotion_eligible=false` regardless of
its score.  No advisor service output was used as a label.

Aggregate report SHA-256:
`884D319808EF1853047A84560CCF8FD68838CEEF5646BA137B0F49F906B342FA`.

## Result

The ranking layer works, but the open-set decision is still the bottleneck.
On the 63,827-query 2023+ development/transfer partition:

- 25,116 of 26,389 known queries have the true identity in the frozen
  candidate set: 95.18% overall candidate recall;
- LambdaMART ranks the true identity first for 24,903 known queries: 94.37%
  overall Top-1 accuracy before NIL rejection;
- after the frozen NIL threshold, known recall is 18,967 / 26,389 = 71.87%,
  known-link precision is 99.905%, and new-author false-link rate is
  106 / 37,438 = 0.283%; and
- the already-open 2022 bucket has 11 / 1,306 new-author false links with a
  one-sided 95% upper bound of 1.619%, so it fails the 0.5% target.

| Method | Known recall | Known-link precision | New false-link | B3 F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|
| Project Two base | 75.20% | 99.554% | 0.801% | 0.7799 | 0.5950 |
| Native graph 0.5 | 84.93% | 99.415% | 1.563% | 0.8083 | 0.6697 |
| Group ranker + NIL gate | 71.87% | 99.905% | 0.283% | 0.7759 | 0.5904 |

The new model is a useful low-risk point but does not dominate the base: it
loses 3.33 recall points and slightly lowers both clustering scores.  It is
not promoted.  The strong pre-gate Top-1 result means the group ranker should
not be discarded; future research should target target-domain, cross-time and
name-block-conditional NIL calibration rather than deeper ranking models.

## Complexity

The ranker uses 120 depth-at-most-4 trees over 28 features.  The NIL gate uses
120 depth-at-most-3 trees over 33 features.  With bounded candidate count `C`,
online tree inference is `O(C*T_rank*d_rank + T_gate*d_gate)` and performs no
full-author-catalog scan.

The first offline implementation took 799.0 seconds, used 2.65 GiB peak
working set and processed the transfer phase at about 126 queries/s.  The
main overhead is currently candidate feature construction:
`O(K^2 + K*profile_context)` because listwise summaries are recomputed for
each of at most 20 candidates.  This must be vectorized/cached before any
runtime consideration.  Model depth must not be increased to hide this
implementation cost.

## Decision

1. Keep the grouped ranker as a model-level research branch, not runtime code.
2. Do not tune more trees or thresholds on the opened public partitions.
3. Reproduce an official S2AND/WhoIsWho baseline next.
4. Use verified ISTINA development labels to learn a time/name-block-aware NIL
   calibration; reserve a separate untouched ISTINA blind test.
5. Consider a set model or edge-refined GNN only if the tree ranker's errors
   remain after adequate target labels and hard negatives are available.

