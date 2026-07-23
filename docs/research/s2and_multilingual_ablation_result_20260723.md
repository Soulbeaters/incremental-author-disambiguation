# S2AND multilingual feature ablation result — 2026-07-23

## Decision

Retain the multilingual name-view family as a **public-development candidate**
for the risk-controlled Project Two model.  It materially improves selective
known-author coverage and clustering quality without increasing observed
new-author false links.  It is not an ISTINA promotion result, does not
validate Palladius/Cyrillic/Han features, and does not establish overall
superiority over official S2AND.

Do not tune the public 2025+ operating threshold again.  The next valid
controls are stock-S2AND retraining on development data and evaluation on
separately partitioned ISTINA development labels.

## Frozen protocol

- Project revision: `9fa59e825f3cadab3e0ee9bd5379ef64866345be`
- Train: history through 2022; query year 2023
- Validation: history through 2023; query year 2024
- Certification: fixed 2024 paper bucket held out from threshold selection
- Public comparison: history through 2024; queries from 2025 onward
- Comparison queries: 15,422; 9,175 known and 6,247 genuinely new
- Candidate universe: unchanged
- Old feature group: `listwise_semantic_cross_profile`
- New feature group: `listwise_multilingual_cross_profile`
- Risk procedure: 64-point training-quantile fixed sequence
- New selected threshold: `0.9629815736647362`
- Threshold frozen and model exported/reloaded before certification: yes
- Frozen bundle schema: `project2_lightgbm_bundle_v2`

Query identities were evaluator-only.  They did not enter candidate
generation, features, ranking or threshold inputs.  The model used only
source-observed structured first/middle/last fields; no synthetic unstructured
name was read.

## Main public-development result

| Method | Known recall | Known prediction precision | Accepted-link precision | New false-link rate | B3 F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|---:|
| Previous semantic selective model | 0.585722 | 0.999256 | 0.996847 | 0.002081 | 0.910298 | 0.707491 |
| Multilingual selective model | **0.683815** | **0.999522** | **0.997456** | **0.002081** | **0.926286** | **0.779050** |
| Official S2AND v1.21 | 0.962943 | 0.982540 | 0.954413 | 0.042420 | 0.990210 | 0.973474 |

Relative to the previous selective model, the new model:

- increases known recall by `0.098093` absolute (`16.75%` relative);
- links 900 additional known queries correctly;
- reduces wrong-known links from 4 to 3;
- leaves new-author false links unchanged at 13 of 6,247;
- increases B3 F1 by `0.015988`; and
- increases Pairwise F1 by `0.071559`.

The known-recall 95% interval is `0.674225--0.693251`.  Known prediction
precision is `0.999522`, with 95% interval `0.998596--0.999837`.

This is a better point on the Project Two selective risk--coverage frontier.
It is not a claim that the method dominates S2AND: official S2AND remains much
stronger in aggregate recall and clustering, but operates at a much higher
new-author false-link rate.

## Risk evidence

The threshold was selected before certification and was not changed after
either certification or the public 2025+ comparison.

| Split and risk | Events / trials | Observed | One-sided 95% upper bound | Target | Pass |
|---|---:|---:|---:|---:|---:|
| Certification new-author false link | 0 / 1,302 | 0 | 0.002298 | 0.005 | yes |
| Certification wrong-known | 0 / 2,003 | 0 | 0.001495 | 0.010 | yes |
| Public comparison new-author false link | 13 / 6,247 | 0.002081 | 0.003827 | 0.005 | yes |
| Public comparison wrong-known | 3 / 9,175 | 0.000327 | 0.001028 | 0.010 | yes |

Both predeclared statistical risk checks pass.  `eligible_for_promotion`
remains false because these are opened public-development labels.

## What produced the gain

The ungated candidate ranker changes only slightly:

| Split | Previous Top-1 | Multilingual Top-1 | Difference |
|---|---:|---:|---:|
| 2024 certification | 0.940090 | 0.940589 | +0.000499 |
| 2025+ comparison | 0.945613 | 0.946049 | +0.000436 |

Therefore the 900-link selective-recall gain comes primarily from better
LINK/NIL calibration, not from a large candidate-ranking improvement.

Non-zero multilingual ranker features, by LightGBM split importance, are:

| Feature | Split importance |
|---|---:|
| family Latin-view similarity | 98 |
| given Latin-view similarity | 71 |
| name-order swap similarity | 68 |
| given-initial compatibility | 57 |
| family native similarity | 45 |
| given native similarity | 40 |

The NIL gate uses name-order swap similarity (12 splits) and given native
similarity (9 splits).  Palladius, Cyrillic-pair, Han-pair, cross-script,
patronymic and short-surname features have zero split importance on this
public dataset.

This matches the independent coverage audit: the public source has almost no
labelled cross-script identities and zero verified Palladius rescue pairs.
The result supports the core structured-name views; it does **not** provide
evidence for the Russian-written Chinese extension.

## Complexity

| Measurement | Previous model | Multilingual model | Change |
|---|---:|---:|---:|
| End-to-end wall time | 803.97 s | 1,136.28 s | +41.3% |
| Peak working set | 4,676,882,432 B | 4,981,194,752 B | +6.5% |
| Final comparison rank phase | 55.01 s | 96.56 s | +75.5% |

The first implementation exceeded a 20-minute process limit because it
recomputed identical profile names once per historical paper.  Deduplicating
structured profile names and caching deterministic per-string views reduced
training candidate construction from 144.38 to 80.37 seconds and validation
selection ranking from 159.79 to 60.90 seconds, while preserving the selected
threshold exactly.  The completed optimized run remains slower than the old
model, and this cost must be included in later scalability analysis.

## Reproducibility

- Aggregate result:
  `runs/project2_late_public_2024_multilingual_fixedseq64_v2/aggregate_result.json`
- Aggregate SHA-256:
  `e6eb9576e244b13935160ee0a2813dfc2bd1e4f7f6c263c02ccbb2a29639c6d9`
- Frozen model:
  `runs/project2_late_public_2024_multilingual_fixedseq64_v2/frozen_model_bundle.json`
- Frozen model SHA-256:
  `e04880ba68916f1ef34bc6185b64898e2914054c19d296be02f351747afa8da7`
- Checkpoint status: complete
- Full repository test suite before the run: 341 passed

The earlier timed-out directory is retained as failure/complexity evidence and
must not be reported as a completed result.

## Next evidence

1. Implement the stock-S2AND retraining control without the Project Two
   multilingual features, using development-only train/validation roles.
2. Do not infer a Palladius benefit from the current public data.
3. On ISTINA development data, preregister Russian, Chinese, Palladius,
   initials, patronymic-missing, short-surname and dense-block subgroups before
   opening outcomes.
4. Compare all methods at the same candidate contract and at matched risk or
   matched coverage.
5. Freeze the target-domain model and protocol before the separate ISTINA
   blind labels are opened.
