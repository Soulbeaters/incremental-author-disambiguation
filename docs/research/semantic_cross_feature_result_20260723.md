# Paper-to-profile semantic cross-feature ablation

Date: 2026-07-23

Status: opened public development ablation; not an ISTINA blind test

## Hypothesis

A query-paper SPECTER vector compared with the historical paper-vector
centroid of each candidate author may improve candidate ranking without
changing candidate generation.

The feature uses only the query paper and papers already present in the
candidate's temporal history. Query identity labels are evaluator-only. The
original 28-dimensional feature group and its NIL gate explicitly exclude the
two new semantic dimensions, so it remains a strict ablation control.

## Data and protocol

- Code revision: `69d25fd`
- Same public Crossref-ORCID/Semantic Scholar replay as the official S2AND
  comparison
- Same 2020 training, 2021 selection/certification and 2022+ comparison roles
- Same 58,987 comparison queries and frozen candidate sets
- Same risk targets and learn-then-test threshold procedure
- Semantic coverage: 100% in every temporal role
- Embedding dimension: 768

Aggregate hashes:

- 28-dimensional control:
  `22796b20d00d680c28048491603a80f6e655b9276578d3f039f7914d586cb7ab`
- 30-dimensional semantic group:
  `77c3beac359a937d316cd9dec8300bfb8a4f3b44b91d98e67d6cecbc90cbdfd0`

No query-level identities, vectors or checkpoint records are committed.

## Ranker result before NIL gating

| Split | Control Top-1 | Semantic Top-1 | Difference |
|---|---:|---:|---:|
| 2020 out-of-fold training | 95.628% | 95.678% | +0.050 pp |
| 2021 threshold selection | 95.019% | 95.168% | +0.149 pp |
| 2021 certification | 93.895% | 94.067% | +0.172 pp |
| 2022+ comparison | 94.333% (24,038) | 94.514% (24,084) | +0.181 pp (+46) |

Final known-candidate recall is identical at 95.161% because retrieval is
frozen. The semantic cosine is the most-used ranker feature by split count,
but the observed Top-1 improvement is small. A paired significance claim is
not made because the current aggregate artifact does not retain pseudonymous
per-query ranker outcomes.

## Selective decision result

| Measure | 28-dimensional control | Semantic group |
|---|---:|---:|
| Selected threshold | 0.95319 | 0.96936 |
| 2021 selection coverage | 27.63% | 19.82% |
| Final known recall | 44.89% | 32.72% |
| Final known-prediction precision | 99.95% | 99.93% |
| Final new-author false-link rate | 0.0806% | 0.0597% |
| Final B³ F1 | 74.61% | 71.20% |
| Final Pairwise F1 | 45.10% | 33.57% |
| Certification new-author events | 2 / 962 | 1 / 962 |
| Certification new-risk upper bound | 0.797% | 0.596% |
| Certification passes 0.5% target | no | no |

The semantic model reduces seven final new-author false links but loses about
3,101 correct known-author links relative to the control. It therefore fails
the registered objective of improving useful coverage at bounded risk.

## Complexity

The directly comparable runs took:

- control: 823.06 wall seconds
- semantic: 830.75 wall seconds

The approximately 7.7-second increase is acceptable for offline fitting and
does not alter online candidate-generation complexity. Complexity is not the
reason to reject this version.

## Conclusion

The hypothesis is only weakly supported at the candidate-ranking layer and is
rejected at the final selective-decision layer. The semantic feature remains
behind an explicit experimental feature group and is not promoted to the
default algorithm.

The result isolates the next problem: the gate tests roughly 2,700
score-derived thresholds and applies Bonferroni correction over the entire
family, raising pointwise confidence to about 99.998%. The semantic signal is
converted mainly into higher rejection rather than useful safe links.

The next iteration should replace this label-safe but overly large threshold
family with a small threshold family fixed from training scores before the
2021 selection labels are examined. This is a statistical calibration change,
not a post-hoc threshold adjustment. It must be evaluated for:

1. selection coverage and registered risk bounds;
2. unchanged candidate/ranker predictions;
3. the already opened certification result, reported only as development
   evidence;
4. final 2022+ risk-coverage and clustering;
5. control and semantic feature groups under the same finite family.
