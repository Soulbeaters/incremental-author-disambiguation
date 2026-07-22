# Literature-guided algorithm roadmap

Status: research decision record, 2026-07-20.  None of the experimental gates
below is enabled in the production pipeline.

## Research question

Can Project Two improve on the source-faithful ISTINA author-disambiguation
proxy under one paired protocol, while preserving high precision for existing
authors and a low false-link rate for genuinely new authors?

The current answer is **not yet**.  Project Two has a much safer open-set
decision than the proxy, but lower known-author recall and slightly lower B3
and pairwise clustering scores.  The experiments below identify the next
high-value signal and rule out premature GNN work.

## What strong published systems actually do

| Source | Reproducible mechanism | Consequence for Project Two |
|---|---|---|
| [S2AND, JCDL 2021](https://arxiv.org/abs/2103.07534) and [official code](https://github.com/allenai/S2AND) | Pairwise LightGBM plus clustering; the current production repository adds a separate incremental linker and an explicit open-set gate with top/second margins and asymmetric error costs. | Keep candidate selection separate from the decision to link.  Calibrate false-link risk explicitly; do not interpret a top candidate as proof of identity. |
| [CONNA, TKDE](https://arxiv.org/abs/1910.12202) and [official code](https://github.com/BoChen-Daniel/TKDE-2019-CONNA) | Joint candidate matching followed by a distinct matching-vs-NIL classifier using paper text and coauthor/profile evidence. | Our `NEW/UNKNOWN` decision is part of the scientific method, not merely an engineering fallback. |
| [IUAD, ICDE 2021](https://arxiv.org/abs/2011.14333) and [official code](https://github.com/papergitgit/IUAD) | Stable collaboration graph plus probabilistic incremental reconstruction. | Preserve the conservative coauthor graph as one evidence channel and test temporal updates separately. |
| [WhoIsWho, KDD 2023](https://arxiv.org/abs/2302.11848) and [official toolkit](https://github.com/THUDM/WhoIsWho) | Large-scale benchmark, handcrafted and semantic features, GBDT ensemble, optional GNN representation, and an explicit NIL threshold. | A GNN is an auxiliary feature generator; it does not remove the need for blocking, ranking, and rejection. |
| [ARCC, The Web Conference 2024](https://openreview.net/forum?id=ZINIh5I5nj) | Iteratively removes/adds uncertain coauthor, institution, and venue edges before contrastive graph representation and HAC. | A GNN should follow relation-quality work.  Noisy or zero-support graphs cannot create missing evidence by themselves. |
| [KDD Cup 2024 public third-place code](https://github.com/yanqiangmiffy/KDD2024-WhoIsWho-Top3) | LightGBM over paper-to-author profile distances; title, abstract, keywords, organization, coauthor, venue, and OAG embeddings.  The repository reports that GroupKFold was slightly stronger and LightGBM beat model fusion. | First build leakage-safe paper-group folds and profile-to-paper cross features.  Large LLM/GNN models are not the first experiment. |
| [KDD Cup 2024 CPU solution](https://github.com/Leo1998-Lu/KDD2024-WhoIsWho) | Five-fold LightGBM with profile text overlap and author/paper embedding differences. | Hard negatives and profile cross-features are a higher-priority use of compute than deeper graph layers. |
| [ADS disambiguation, Scientometrics 2021](https://link.springer.com/article/10.1007/s11192-021-03951-w) and [code](https://github.com/helenamihaljevic/ads_author_disambiguation) | Random Forest pair scores plus label propagation; deliberately imbalanced negatives and manually labelled dense name blocks; micro/macro B3 F1 are both reported. | Evaluate dense surname blocks, retain interpretability, and report macro as well as micro clustering quality. |
| [LAND, Scientometrics 2022](https://link.springer.com/article/10.1007/s11192-022-04426-2) and [code](https://github.com/sntcristian/and-kge) | Multimodal knowledge-graph embeddings over structure and literals, followed by blocking and HAC. | Text, venue, institution, and graph relations should be distinct ablations before any heterogeneous embedding claim. |
| [ORCID-labelled data audit, Scientometrics](https://link.springer.com/article/10.1007/s11192-020-03826-6) | ORCID-linked ground truth is large but biased toward newer researchers and smaller/easier blocks. | Crossref+ORCID is a useful transfer benchmark, not sufficient evidence of superiority inside ISTINA. |

## There is no universally optimal AND algorithm

The literature separates at least three different problems.  From-scratch
name disambiguation (SND) clusters all papers in one ambiguous name block;
real-time name disambiguation (RND) links a new paper to an existing profile or
to a genuine `NIL`; incorrect-assignment detection (IND) finds papers already
placed in the wrong profile.  A method optimized for transductive SND is not
automatically valid for incremental open-set RND.  The optimum also changes
with available title/abstract/organization fields, block density, graph edge
quality, language and the true NIL prevalence.

Project Two is RND.  Its next model experiment is therefore a compact
two-stage model, not a larger end-to-end service:

1. freeze blocking and the candidate cap, then train a group-aware
   LightGBM/LambdaMART ranker on candidates from the same query and name block;
2. train a separate cost-sensitive `MERGE`-versus-`NIL/UNKNOWN` gate on the
   top score, top--second margin, entropy, block density, temporal/profile
   compatibility and proposal source;
3. calibrate that final decision by time and name-block density, and certify
   the frozen operating point on independent labels; and
4. compare logistic, tree ranker and tree-ranker-plus-NIL variants under the
   same candidates, labels and complexity budget.

This changes the hypothesis class and learning objective: candidate relevance
is learned listwise inside a query group, while false-link risk is optimized
separately.  It remains small enough for ISTINA: with bounded candidate count
`C`, `T` shallow trees and depth `d`, ranking is `O(C*T*d)` and rejection is
constant-size scoring.  A DeepSets/Set-Transformer candidate model is a later
alternative only if verified target-domain training volume is sufficient.
Vanilla GNN or language-model fine-tuning is not the next default.

The local directory described as the old ISTINA “GNN” was also audited.  Its
graph-similarity service constructs a keyword co-occurrence graph and combines
Node2Vec/Word2Vec-derived features with CatBoost.  It is useful prior art for a
topic-evidence channel, but it is not an end-to-end author-disambiguation GNN.
The actual incumbent author algorithm remains the C++ paper-level hypergraph
combination search reproduced by the frozen Python proxy.

## Paired evidence already obtained

All numbers below use real Crossref `given/family` fields and ORCID as a hidden
label.  The synthetic `original_name` column is deleted before model objects
are created.  Raw affiliation is ablated because no normalized institution ID
is available.

Frozen history is 4,118 mentions through 2021.  The test partition contains
11,820 mentions from 2023 onward: 1,579 identities seen in history and 10,241
unseen identities.

| Method | Known correct / 1,579 | Wrong known | New false links / 10,241 | B3 F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|
| ISTINA hypergraph proxy | 1,534 (97.15%) | 10 | 269 (2.627%) | 0.8555 | 0.4919 |
| Project Two base, frozen calibrated threshold 0.995 | 1,280 (81.06%) | 1 | 33 (0.322%) | 0.8419 | 0.3556 |
| Project Two native coauthor graph, support 0.5 | 1,442 (91.32%) | 1 | 39 (0.381%) | 0.8507 | 0.4528 |
| Layered pointwise+topic gate, zero validation errors | 1,476 (93.48%) | 1 | 47 (0.459%) | 0.8520 | 0.4601 |

The layered topic gate adds 34 correct known-author links over the native graph
(exact McNemar p = 1.16e-10), but also adds eight unseen-author false links
(p = 0.0078125).  It is a real precision/recall tradeoff, not a dominance
result, and is therefore **not promoted**.

The less conservative gate adds 57 correct links but 22 false links.  A gate
that replaces rather than layers over the native graph can lose up to 141
correct links.  These negative results prevent threshold cherry-picking.

## What the error structure says

Before graph rescue, the proxy is correct while Project Two is not on 264
known mentions.  Project Two still retrieves the gold identity for 243 of
them, and the gold identity is rank 1 for 223.  The main bottleneck is therefore
not candidate generation.  It is deciding when medium/exact name evidence plus
sparse context is sufficient to link.

The native coauthor graph supplies the largest validated gain so far: 162
additional correct known links on the frozen test, at six added new-author
false links.  The remaining hard cases often have zero coauthor-graph support.
Title, abstract, and venue evidence can recover some of them, but the current
gate does not calibrate across years reliably.

The original temporal training slice contained only 37 residual graph
proposals, 15 positive.  Leakage-safe five-fold paper grouping through 2021
increased this to 157 proposals, 100 positive; after preserving the native
threshold, only 97 residual proposals remained, with 40 positive and 57 unseen
negative examples.  That is too small for a stable 17-24 feature open-set
model, much less a GNN.

## Improvement order

1. **Freeze the native graph result as the current research baseline.**  It is
   the only large, statistically supported gain that remains close to the
   false-link risk of the base method.
2. **Improve the training signal, not model depth.**  Collect verified hard
   negatives and repeated ISTINA identities in dense same-name blocks.  Train
   a cost-sensitive tree/reranker with group-by-paper and group-by-person
   separation.  Report calibration by year and surname-block density.
3. **Promote paper-to-profile cross features only after transfer validation.**
   The local Crossref cache has 100% title, 99.4% venue, and 62.2% abstract
   coverage for 2,276 labelled DOI works.  ISTINA should expose the analogous
   title, venue, keywords/abstract, normalized organization ID, and coauthor
   evidence.
4. **Handle the remaining blocking misses separately.**  Use verified aliases,
   transliteration-aware given/family compatibility, and surname-frequency
   risk.  Do not relax the open-set gate to solve a blocking problem.
5. **Start a GAT/GraphSAGE ablation only when there are enough verified
   relations and hard negatives.**  Use paper, author, organization, venue,
   topic, and time as typed relations; apply ARCC-style edge refinement; feed
   the learned graph score into the same calibrated gate.  Compare it against
   the native graph and topic/tree model, never against the base alone.

## Minimum ISTINA data gate

No further ISTINA superiority claim should be made from the current 25 known
transfer cases.  A useful low-burden pilot export is:

- at least 300 verified repeated-author mentions and 1,000 verified new/unseen
  mentions;
- stable `person_id`, article ID, author position, year, structured
  family/given/middle fields, and an explicit `NEW/UNKNOWN` label where
  appropriate;
- title plus venue and, where available, keywords/abstract;
- coauthors and normalized organization ID (raw affiliation may be included
  but is not treated as a stable identity key);
- deliberate coverage of Chinese/Russian transliterations, initials, short
  surnames, common surnames, and dense same-name blocks;
- no fabricated display name and no use of `original_name`.

For a paper-grade false-link estimate near 0.5%, the target should grow toward
1,000 known mentions and 5,000 unseen mentions, including at least 300 hard
same-name negatives.  This is an algorithmic evaluation export; load testing
or a new production service is not required.

## Decision

Keep the topic/listwise implementation under `experiments/` as a reproducible
negative/Pareto ablation.  Do not enable it in the runtime, do not claim that
Project Two already outperforms ISTINA, and do not begin a large GNN training
run until the ISTINA data gate or an equivalently strong independent labelled
benchmark is satisfied.

The 2026-07-22 selective-veto experiments further show why threshold-only
iteration must stop.  An uncorrected 26-feature logistic gate dominated the
Project Two base on the already-open public transfer benchmark, but failed its
independent new-author certificate.  Familywise-corrected selection reduced
runtime from 511.8 to 324.4 seconds yet lowered known recall to 74.77%, below
the 75.20% base.  The logistic coefficient/threshold line is exhausted as the
main research direction; the next controlled experiment is the two-stage
ranker plus explicit NIL gate above.

That two-stage experiment has now been run.  LambdaMART reaches 94.37% overall
Top-1 accuracy on known 2023+ queries under the frozen candidate set, but the
risk-bounded NIL gate lowers final known recall to 71.87%.  This confirms that
the model-level ranking change is useful while cross-time open-set calibration
remains the limiting scientific problem.  The model is not promoted; see
[grouped_ranker_result_20260722.md](grouped_ranker_result_20260722.md).

The official S2AND `0.51.1` / production-model `v1.21` comparison is also now
version-frozen.  Its promoted incremental linker uses 53 row features, fixed
top-25 cluster retrieval, and a separate calibrated gate.  It requires full
paper context, history-only seed clusters, and SPECTER2 embeddings, so a
name-only or zero-filled invocation would not be a valid strong baseline.  The
fair adapter and evaluation contract are recorded in
[s2and_official_baseline_adapter_audit_20260723.md](s2and_official_baseline_adapter_audit_20260723.md).

The required public context has now been assembled without changing labels or
candidates.  Semantic Scholar batch enrichment over all 29,360 public DOI keys
matched 25,344 works and returned 22,549 SPECTER2 vectors.  The strict
paper-grade subset contains 108,905 labelled authorships, 20,329 papers and
39,759 identities; 13,238 identities occur on at least two papers.  With a
2021 history cutoff it yields 31,209 known and 41,920 new-author queries.  This
removes public sample size as the blocker to S2AND reproduction, but the whole
set remains opened development evidence and cannot certify the final claim.
