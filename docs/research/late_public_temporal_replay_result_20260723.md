# Late public temporal replay result (2026-07-23)

## Decision

Freeze the current semantic-cross-feature, fixed-sequence selective model.  Do
not continue threshold tuning or add stage-specific vetoes on the public replay.
The model is supported as a **risk-controlled high-precision operating mode**,
not as a generally superior replacement for S2AND or the Project Two native
graph pipeline.

Promotion remains forbidden until a held-out ISTINA export is evaluated once.

## Frozen protocol

- Project revision: `504cd87b314abffd1871102ee0f1e06065000e35`
- Training: history through 2022; 2023 queries
- Validation: history through 2023; 2024 queries
- Final public comparison: history through 2024; 2025+ queries
- Training groups: 13,297
- Comparison queries: 15,422 (9,175 known; 6,247 new)
- Feature group: `listwise_semantic_cross_profile`
- Risk procedure: `training_quantile_fixed_sequence`
- Requested/realized threshold grid: 64/41
- Tested fixed-sequence points: 22
- Selected threshold: 0.9629643480633046
- Risk targets: new-author false-link rate <= 0.005; wrong-known-link
  rate <= 0.01; confidence 0.95
- Query labels were evaluator-only.  They were not available to candidate
  generation, ranking features, or the online pipeline.

The temporal boundaries are now command-line parameters with a strict
non-overlap validator.  The full repository test suite passed: 329 tests.

## Same-query comparison

| Method | Known recall | Known prediction precision | Accepted-link precision | New false-link rate | B3 F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|---:|
| Project Two base | 0.812098 | 0.982204 | 0.962786 | 0.024492 | 0.936746 | 0.816416 |
| Project Two native graph | 0.903869 | 0.980028 | 0.948096 | 0.045622 | 0.951674 | 0.872095 |
| Current selective model | 0.585722 | 0.999256 | 0.996847 | 0.002081 | 0.910298 | 0.707491 |
| Official S2AND | 0.962943 | 0.982540 | 0.954413 | 0.042420 | 0.990210 | 0.973474 |

The current model linked 5,374 known queries correctly, linked 4 known queries
to the wrong identity, rejected 3,797 known queries, and falsely linked 13 of
6,247 new-author queries.  Its low false-link rate is real but is purchased
with substantially lower coverage and clustering quality.

The ungated ranker itself remained stable across time:

| Split | Candidate recall | Known-author top-1 accuracy |
|---|---:|---:|
| 2023 training/OoF | 0.953934 | 0.950969 |
| 2024 threshold selection | 0.959881 | 0.954681 |
| 2024 certification | 0.947079 | 0.940090 |
| 2025+ comparison | 0.948665 | 0.945613 |

This indicates that the principal recall loss comes from the conservative NIL
gate, not from an inability to rank a retrieved candidate.

## Risk evidence

The threshold was fixed before the certification bucket was evaluated.

- 2024 certification:
  - unseen false links: 0/1,302; one-sided upper bound 0.002298
  - wrong-known links: 0/2,003; one-sided upper bound 0.001495
  - both predeclared risk limits passed
- 2025+ opened public comparison:
  - unseen false links: 13/6,247; upper bound 0.003827
  - wrong-known links: 4/9,175; upper bound 0.001206
  - both predeclared risk limits passed

The comparison labels are still an opened public development resource, not an
independent ISTINA blind test.  Therefore `eligible_for_promotion` remains
false even though the statistical risk checks passed.

## Reproducibility

- Current result:
  `runs/project2_late_public_2024_semantic_fixedseq64/aggregate_result.json`
- Current result SHA-256:
  `0057999756021AF66B9B18CE95153183220F2DF4ADDBA5983D26383C5271C541`
- Official comparator:
  `runs/s2and_official_python_2024_full/aggregate_result.json`
- Official comparator SHA-256:
  `F57ECC8212C28D22FDBA281CBDCDA8335E3C387A17860BF79266CBE77D5DAF8E`

Both methods evaluated exactly 15,422 query authorships.  The official S2AND
run completed 8,027 blocks in about 8.5 minutes; the Project Two comparison
completed in about 20.2 minutes.  These are observed end-to-end research
runtimes, not service throughput claims.

## Stop rule and next evidence

No more public-replay parameter tuning is justified.  In particular:

- do not learn a veto from the sparsely supported candidate-rescue stage;
- do not select a lower gate threshold after seeing 2025+ outcomes;
- do not claim overall superiority from the precision/risk result;
- do not promote the model based on public development data.

The next valid experiment is a single frozen evaluation on the independent
ISTINA export, reported both at the same operating threshold and at comparable
coverage/risk operating points.  If the ISTINA blind result fails either risk
limit or does not preserve the precision advantage, stop this model family and
redesign the NIL/open-set model rather than resume parameter search.
