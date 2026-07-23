# RuZh profile-consensus and collision-hard-negative method — 2026-07-23

## Status and claim boundary

This is a preregistered public-development method, not a completed result.
No SOTA, official-S2AND superiority or ISTINA superiority claim is currently
allowed.  The advisor's final blind-test labels remain unavailable to
training, feature selection, threshold selection and method selection.

The public official-S2AND checkpoint has now been audited without rerunning
inference.  The frozen 2025+ comparison contains 5,068 target-stratum queries:
3,158 known and 1,910 genuinely new.  Official S2AND obtains 0.944902 known
recall, 0.968202 known-link precision, 0.031032 wrong-known rate and 0.102618
new-author false-link rate.  Its target B³ F1 is 0.980521 and Pairwise F1 is
0.956610.  These are development metrics, but they expose a concrete target:
retain the strong known recall while reducing false merges in high-collision
Chinese/Russian name blocks.

## Literature-to-method synthesis

- [S2AND](https://arxiv.org/abs/2103.07534) shows that training across several
  heterogeneous datasets improves out-of-domain robustness and uses a
  pairwise GBT followed by agglomerative clustering.  Project Two therefore
  retains the strong pairwise baseline and evaluates transfer rather than
  replacing it with a weak local proxy.
- [WhoIsWho, KDD 2023](https://arxiv.org/abs/2302.11848) provides more than one
  million papers, is deliberately rich in ambiguous Chinese names, and finds
  that coauthor relations plus semantic and organization evidence are
  complementary.  Project Two treats it as the next independent public
  transfer benchmark.
- [Bridging the Language Gap, 2026](https://arxiv.org/abs/2604.03776) improves
  Chinese-name recall by combining coauthor, affiliation, citation and content
  evidence across character and Pinyin representations.  Its 80-pair
  evaluation is too small to establish a strong general benchmark, but its
  multi-view and multi-evidence hypothesis is directly relevant.
- [Ditto, PVLDB 2021](https://www.vldb.org/pvldb/vol14/p50-li.pdf) gains from
  domain-knowledge injection and difficult-example augmentation.
  [Sudowoodo](https://arxiv.org/abs/2207.04122) shows that contrastive
  pretraining can exploit unlabeled entity records before supervised
  fine-tuning.  Project Two adopts the lower-complexity part now: explicit
  multilingual views and collision-aware hard negatives; a neural contrastive
  encoder remains a later ablation, not an assumed improvement.
- [Bootleg, CIDR 2021](https://vldb.org/cidrdb/2021/bootleg-chasing-the-tail-with-self-supervised-named-entity-disambiguation.html)
  demonstrates that rare/tail entities need a representation and objective
  designed for the tail rather than only global accuracy.  Project Two reports
  target-stratum and open-set errors separately.

## Frozen hypothesis

The prior Project Two ranker selects the single best historical name view.
That helps recall, but one accidental match can dominate a profile.  The new
method adds six label-free profile summaries over distinct, source-observed
structured names:

1. profile view count;
2. mean joint family/given support;
3. rate of strongly compatible views;
4. explicit Chinese/Russian lexicon-conflict rate;
5. cross-script support rate; and
6. support-minus-conflict consensus margin.

Training additionally weights a negative candidate by
`1 + 3 * target * hardness * (1 - conflict)`, capped implicitly at four.
`hardness` is the larger of the best pairwise name compatibility and the
profile mean support.  Positives retain unit weight.  The weight is computed
only from feature values and the training label; it is never an inference
feature and never reads the advisor service prediction.

This changes the learning objective, not only a decision threshold.  It asks
the ranker to spend more capacity separating homonymous authors inside
Chinese/Russian collision blocks while profile consensus prevents a single
alias from forcing a merge.

## Single public ablation

The only new development comparison is:

- control: `listwise_multilingual_cross_profile`;
- new method: `listwise_ruzh_profile_hard_negative`.

Train is history through 2022/query 2023; validation is history through
2023/query 2024 with a paper-level certification bucket; comparison is history
through 2024/query 2025+.  Candidate retrieval, SPECTER2 inputs, non-name
features, LightGBM capacity, fixed-sequence risk procedure and 64-point
threshold family stay unchanged.

Report overall and target-stratum known recall, known prediction precision,
wrong-known, new-author false links, B³/Pairwise, candidate Top-1, runtime,
memory and feature importance.  Do not tune the method after reading the
2025+ comparison.  If it fails to improve the frozen target frontier, retain
it as a negative result and move to the preregistered WhoIsWho transfer step
instead of adjusting parameters repeatedly.

## Complexity

For `V` distinct structured name views in a candidate profile, consensus
features add `O(V)` time and `O(1)` output space.  Candidate generation and its
asymptotic complexity do not change.  The training weights add `O(C)` work for
`C` materialized candidate rows and no inference cost.

## Final ISTINA rule

After public development, the advisor data is partitioned before use:
development train/validation/certification may support target adaptation, but
the final blind test is sealed.  The blind labels are opened exactly once
after code, feature schema, model artifact, threshold and comparison protocol
are frozen.  Any later method change invalidates that blind result.
