# RuZh profile-consensus hard-negative result (2026-07-23)

## Decision

Do not promote this model.  The registered change improved the previous
Project Two multilingual selective model on recall and clustering, but it did
not preserve all error outcomes and it remains substantially below official
S2AND.  It is evidence that profile-name consensus is learnable, not evidence
of SOTA or of superiority over S2AND.

This was the only run of the preregistered feature/objective ablation.  No
threshold or hard-negative weight was changed after the 2025+ comparison was
opened.

## Frozen public protocol

- Code revision: `cff5ccb`
- Training: history through 2022, queries from 2023
- Validation selection/certification: history through 2023, queries from 2024
- Opened public comparison: history through 2024, queries from 2025+
- Comparison: 15,422 queries (9,175 known; 6,247 new)
- Feature group: `listwise_ruzh_profile_hard_negative`
- Selected threshold: `0.9561207026473063`
- Candidate universe and model capacity were unchanged.
- The advisor's future ISTINA blind test was not accessed.

## Result

| Method | Correct known | Wrong known | False links to new | Known recall | Known prediction precision | New false-link rate | B3 F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Previous Project Two multilingual selective | 6,274 | 3 | 13 | 0.683815 | 0.999522 | 0.002081 | 0.926286 | 0.779050 |
| Profile consensus + collision hard negatives | 6,369 | 5 | 20 | 0.694169 | 0.999216 | 0.003202 | 0.929507 | 0.792621 |
| Official S2AND | — | — | — | 0.962943 | 0.982540 | 0.042420 | 0.990210 | 0.973474 |

Against the previous Project Two model, the new model recovered 95 additional
known queries and improved B3 by 0.003221 and Pairwise F1 by 0.013571.  It also
introduced two additional wrong-known links and seven additional new-author
false links.  The joint non-regression contract therefore fails.

The opened Project Two target detector selected 5,574 Russian/Chinese-shaped
queries.  On this stratum the model obtained 0.500727 known recall,
0.998262 known-prediction precision, 0.003751 new false-link rate,
0.884048 B3 F1 and 0.649933 Pairwise F1.  This target cohort is not directly
identical to the conservative all-target-block S2AND audit, so those target
numbers must not be presented as a paired superiority comparison.

## Interpretation

The ranker still achieved 0.945831 top-1 known accuracy before the NIL gate,
whereas the deployed selective decision achieved only 0.694169 known recall.
The dominant loss is therefore open-set acceptance, not candidate ordering.
Profile consensus features received substantial split importance
(`profile_name_support_rate_085`: 69; `profile_name_support_mean`: 48;
`profile_name_consensus_margin`: 39), so the signal is real, but the current
standalone architecture cannot turn it into an across-metric improvement.

The next experiment is structural rather than another threshold sweep:

1. keep official S2AND as the exact default prediction;
2. learn a Russian/Chinese residual expert only from earlier temporal splits;
3. allow corrections only in prespecified S2AND error regions;
4. require identical non-target outputs, no decrease in correct known links,
   no increase in wrong-known links or new-author false links, and at least one
   strict target improvement on the frozen 2025+ public comparison.

## Reproducibility

- Local aggregate:
  `runs/project2_late_public_2024_ruzh_profile_hardneg_v1/aggregate_result.json`
- Aggregate SHA-256:
  `080F99B9C483F1431B7183E68817839D1B5FEBB7609F6A460612C3BC592E1052`
- Frozen model SHA-256:
  `43122A8382FFF9C8FE7F82AF2FA37C1E3E17F0333DF0112B97200E92C748FE52`
- Compact record-free evidence:
  `evidence/ruzh_profile_hard_negative_20260723.json`
- Full test suite before the formal run: 371 passed.
