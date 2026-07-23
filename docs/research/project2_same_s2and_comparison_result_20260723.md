# Project Two on the official S2AND public replay

Date: 2026-07-23
Status: opened public development evidence; not an ISTINA blind test

## Question

Can the current Project Two core improve open-set merge safety while retaining
enough known-author recall and clustering quality to compete with the official
S2AND reference on exactly the same public replay?

This experiment holds input authorships, temporal roles, query set and public
labels fixed. It does not use service predictions as truth and does not use the
synthetic `original_name` field.

## Frozen protocol

- Project revision: `10c1f17`
- History for ranker development: through 2019
- Ranker/NIL-gate training queries: 2020
- Threshold selection: four fifths of 2021 papers
- Opened certification partition: one fifth of 2021 papers
- Development comparison: history through 2021, all 2022+ queries
- Comparison queries: 58,987
  - known-author queries: 25,482
  - new-author queries: 33,505
- Ranker: grouped LambdaMART, 28 features
- NIL decision: binary gate, 33 features
- Selected acceptance threshold: 0.95319186324702
- Target new-author false-link rate: at most 0.5%
- Target wrong-known rate: at most 1.0%
- Threshold-selection confidence: 95% familywise

Input hashes:

- authors:
  `3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`
- article-author map:
  `d72534f2053275833fbd6bc4ea14c8bf17ada73f0b95130c397e9a4b50260ba9`
- official S2AND aggregate:
  `0ae63baa48cfb5fd9a7606e80fd0c50d6e6345f53a071e9e959d5bc195bcdd35`

Runtime:

- Python 3.12.7
- Levenshtein 0.27.3
- LightGBM 4.6.0
- NumPy 1.26.4
- scikit-learn 1.5.1

The private aggregate result has SHA-256
`c5777fbf8159cae28ea38fb44c6cdd707800dfb88f9debdf4badb0b538fd4dd7`.
It contains aggregate evidence only. Query-level checkpoints remain ignored
locally and are not committed.

## Results

| Method | Correct known | Wrong known | Known abstentions | False links on new | Known recall | Known-prediction precision | Accepted-link precision | New false-link rate | B³ F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Project Two base | 19,463 | 224 | 5,795 | 526 | 76.38% | 98.86% | 96.29% | 1.570% | 82.13% | 64.35% |
| Project Two native graph | 22,157 | 259 | 3,066 | 728 | 86.95% | 98.84% | 95.74% | 2.173% | 85.10% | 72.56% |
| Project Two grouped selective | 11,439 | 6 | 14,037 | 27 | 44.89% | 99.95% | 99.71% | 0.0806% | 74.61% | 45.10% |
| Official S2AND Python reference | 24,600 | 288 | 594 | 594 | 96.54% | 98.84% | 96.54% | 1.773% | 98.76% | 98.31% |

The Project Two grouped decision is significantly safer than the native graph
on new authors: it prevents 701 native-graph false links without introducing a
new error in the opposite direction
(`McNemar p = 1.90e-211`). The cost is severe abstention: on known authors the
native graph is correct in 10,718 cases where the grouped decision is not, and
there are zero cases in the opposite direction (`McNemar p` numerically zero).

The 2020 out-of-fold training diagnostics were stronger than the final
selective result:

- 8,950 training queries and 8,085 non-empty candidate groups
- known-candidate recall: 96.21%
- ranker Top-1 known accuracy: 95.63%
- input-order Top-1 known accuracy: 86.88%

This gap is evidence of temporal calibration/coverage failure, not evidence
that candidate ranking alone is solved.

## Risk checks

Threshold selection used 8,931 opened 2021 queries. At the selected threshold:

- accepted: 2,468
- correct known: 2,464
- new false links: 3
- wrong-known links: 1
- coverage: 27.63%
- selected upper bound for new false links: 0.460%
- selected upper bound for wrong-known links: 0.310%

The separate 2021 certification partition did **not** pass the registered risk
gate:

- new authors: 962; false links: 2; observed 0.208%
- one-sided 95% upper bound: 0.797%, above the 0.5% target
- known authors: 1,163; wrong-known links: 0
- one-sided 95% upper bound: 0.257%, below the 1.0% target

The larger 2022+ development comparison has lower observed risks and both
upper bounds pass, but it cannot retroactively replace the failed fixed
certification partition:

- new false-link upper bound: 0.1247%
- wrong-known upper bound: 0.0555%

Therefore the current model is not eligible for promotion or a safety claim.

## Complexity and reproducibility

- End-to-end wall time: 775.45 seconds
- CPU time: 757.52 seconds
- Peak working set: 3,190,988,800 bytes
- Final candidate groups: 55,154
- Final Project Two decision time: 425.25 seconds
- Mean candidate pool: 73.45
- Mean scored candidates: 40.85
- Truncated candidate pools: 13,426

The earlier implementation timed out after one hour because affiliation
Levenshtein distance used a pure-Python quadratic loop. On an identical
200-query slice, exact C-extension distance reduced decision time from
83.21 seconds to 2.09 seconds. A 50-query real replay produced identical
records, candidates, scores, graph proposals and decisions after latency was
removed; both variants hashed to
`8e6d05af4c69bdc9126b6f7a7d3acc69c06755908cf1d22690fd4697a015c687`.

Formal replay now writes protocol-bound atomic checkpoints every 5,000
queries. Checkpoints validate the code revision, input hashes, runtime
versions, parameters and mention hashes before reuse.

## Interpretation

The current evidence is a negative result against the broad superiority claim:

1. S2AND strongly dominates all Project Two variants in known-author recall
   and clustering quality on this public development replay.
2. The native graph adds recall but also increases new-author false links.
3. The grouped model currently behaves as a selective veto, not as a better
   identity ranker on the final period. Its useful contribution is risk
   reduction, bought with excessive abstention.
4. The fixed certification split fails the registered 0.5% new-author risk
   target. The 2022+ result remains development evidence only.

No paper should claim that this version exceeds S2AND or is ready for ISTINA.

## Next falsifiable iteration

The next change should target risk at useful coverage, not another threshold
adjustment:

1. Add leakage-safe paper-to-profile cross features using the existing
   SPECTER paper vectors: query paper versus historical papers of each
   candidate profile, with no query identity label in feature construction.
2. Train with temporally forward hard negatives from the same name block,
   including graph-supported wrong candidates, rather than relying on random
   within-year paper folds alone.
3. Refit the candidate ranker and NIL gate with explicit temporal calibration,
   then report the full risk-coverage curve. The 2021 certification partition
   remains fixed and may not be used for training.
4. Run ablations for semantic cross features, graph evidence, temporal
   features and the selective gate on the same candidates.
5. Reject the new method unless it improves known recall/B³ at the registered
   risk bound and preserves complexity suitable for ISTINA embedding.

GNN work remains deferred. The current graph result shows that relation
evidence is useful but unsafe; a GNN is justified only after robust edge
quality and open-set error control are formulated and tested.
