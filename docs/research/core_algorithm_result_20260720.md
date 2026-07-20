# Core algorithm result — 2026-07-20

## Frozen protocol

- History: Crossref records through 2021.
- Validation: 2022 only.
- Test: 2023 and later, evaluated after both thresholds were frozen.
- Input features: structured given/family name, paper, year, affiliation and coauthor context.
- ORCID/person ID: label only, never a feature.
- The advisor export's synthetic display-name column is removed before model objects are created.

The calibrated candidate threshold is `0.995`. The native paper-graph rescue is allowed only for `UNKNOWN` or `NEW`, requires structured-name compatibility, and requires historical graph support of at least `0.5`.

## 2023+ Crossref/ORCID transfer test

The test contains 11,820 mentions: 1,579 identities seen in history and 10,241 identities not seen in history.

| Method | Known recall | Precision among known-ID predictions | Unseen-author false-link |
|---|---:|---:|---:|
| Frozen ISTINA hypergraph proxy | 97.15% | 99.35% | 2.63% |
| Project Two base | 81.44% | 99.92% | 0.46% |
| Project Two calibrated + native paper graph | **91.45%** | **99.93%** | **0.52%** |

The prespecified context ablation found that raw affiliation strings did not
transfer safely.  The frozen no-affiliation profile retained 91.32% known
recall and 99.93% known-prediction precision while reducing unseen-author
false-link to **0.38%**.  This is the recommended cross-domain safety profile;
affiliation may be reintroduced only after institution entity normalization.

The native graph recovers 158 additional correct known-author links over the Project Two base while adding six unseen-author false links. The paired known-author improvement over the base is significant by exact McNemar test (`p = 5.47e-48`). The 95% Wilson intervals are 89.97%–92.73% for known recall and 0.40%–0.68% for unseen-author false-link rate.

This is a safer precision/recall trade-off, not an across-the-board win over the incumbent proxy. The proxy retains higher known-author recall; Project Two has much lower unseen-author false-link and higher prediction precision.

## Advisor ISTINA transfer diagnostic

After exact de-duplication, missing-label removal, structured-field validation and exclusion of the synthetic display name, the 90-paper export yields only 25 linkable known-author test mentions. The proxy is correct on 20 and Project Two on 14. This sample is too small for a superiority claim and does not currently favor Project Two.

## Rejected ablations

- Accepting a zero-support unique candidate: rejected because validation unseen-author false-link rose to 2.33%.
- Running graph search over the unfiltered local top-k: rejected because noisy candidates overwhelmed graph evidence.
- GNN: deferred until the non-neural baseline and independent ISTINA labels are sufficient.

## Frozen-history clustering

On the same 2023+ partition, the native graph raises B³ F1 from 0.8420 to
0.8506 and pairwise F1 from 0.3574 to 0.4529.  The no-affiliation safety
profile obtains B³ F1 0.8507, pairwise F1 0.4528 and a 2.86% identity-conflict
cluster rate, compared with 13.92% for the ISTINA proxy.  Unresolved mentions
are singletons; these are online frozen-history clustering metrics, not a
claim that unseen identities are dynamically clustered.

Five- and ten-year coauthor-edge half-lives were neutral on validation, so
time decay is not enabled in the frozen method.
