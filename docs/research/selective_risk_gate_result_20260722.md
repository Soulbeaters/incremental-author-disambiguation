# Selective risk-gate development result — 2026-07-22

## Status

This is a public-data development result, not a final ISTINA test and not a
promoted runtime configuration.  Crossref--ORCID 2023+ has already influenced
the project and is explicitly classified as a development/transfer benchmark.
The advisor services are not labels and were not used in these experiments.

The source contains 120,815 usable real structured authorships and has SHA-256
`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`.
Training used 2021, threshold selection used four paper-hash buckets from
2022, and the fifth 2022 bucket was opened only after each threshold was
frozen.  The development/transfer comparison contains 63,827 queries from
2023 onward.

## Hypothesis and implementation

The previous residual gate could add graph links but could not remove unsafe
base `MERGE` decisions.  The new selective gate represents both base merges
and graph proposals as candidate decisions, then either accepts or abstains.
It adds inexpensive temporal profile, paper-to-profile coauthor containment
and candidate-distribution uncertainty features inspired by the feature
families used in the official [S2AND](https://github.com/allenai/S2AND) and
[WhoIsWho](https://github.com/THUDM/WhoIsWho) pipelines.

The experiment compares four nested feature groups (6, 11, 18 and 26
features).  It never changes the candidate universe, candidate cap or graph
beam, so improvements cannot come from searching more of the database.

## Three preregistered operating points

| Gate | Selected features | Independent new-author risk | Independent wrong-known risk | 2023+ known recall | 2023+ new false-link | Decision |
|---|---:|---:|---:|---:|---:|---|
| Residual gate, no base veto | 18 | 17/1,306; upper95 2.224% | 9/2,040; upper95 0.903% | 77.17% | 0.804% | fail |
| Base veto, zero validation errors | 6 | 0/1,306; upper95 0.229% | 0/2,040; upper95 0.147% | 12.86% | 0.182% | risk passes, coverage unusable |
| Base veto, pointwise validation-bound selection | 26 | 12/1,306; upper95 1.722% | 5/2,040; upper95 0.618% | 84.04% | 0.654% | useful exploratory frontier, certification fails |

The third gate is the important scientific signal.  On the 2023+ development
benchmark it improves the base method from 75.20% to 84.04% known-author
recall while reducing new-author false links from 0.801% to 0.654%.  It also
improves B3 F1 from 0.7799 to 0.8103 and Pairwise F1 from 0.5950 to 0.6800.
Against the native graph rule it gives up 0.90 recall point but cuts new false
links from 1.563% to 0.654% and improves both clustering scores.

This is development-set dominance over the Project Two base, not evidence of
ISTINA or public-baseline superiority.  The independent certification failure
means the 26-feature model and threshold are not promoted.

Aggregate report hashes:

- residual: `540D70BBB8D6A55590A618256D767FA9C540217E2CDCDDE12C3A3EA289530C2A`;
- zero-error veto: `626CFC669BA6252967C9C63D13178373DFE73985B0EB075264B06405DC98066A`;
- risk-bounded veto: `D4C708FC6E33BFA5C08079726FB3D3FA97D89EC0B79BFF4904C6127466BE011F`.

The optimized familywise-controlled rerun (labels already opened and therefore
development-only) selected 26 features, reached 74.77% known recall and 0.374%
new false-link rate, and took 324.4 seconds.  Its aggregate report hash is
`4B008F06FC0D91E33F5E146D2D72A03B2DFAEE492BEE548A92FA6BF7531C1B7C`.
Because recall is below the 75.20% base, this more rigorous logistic operating
point is not useful.  Further coefficient or threshold tuning is stopped.

## Complexity result

With `H` history mentions, at most `C=100` retrieved candidates, `K=20`
retained candidates, `A` authors on the incoming paper, graph beam `B=256`
and gate dimension `D<=26`:

- history construction is `O(H + sum_p A_p^2)` time and `O(H + E)` space;
- indexed candidate lookup plus deterministic ordering is
  `O(sum posting lengths + C log C)` per query;
- bounded candidate scoring is `O(C)` per query;
- paper-graph search is `O(B*C*A^2)` per paper;
- the selective gate adds `O(K + profile context + D)` per query and no
  full-catalog scan; and
- the recorded development runs used 2.77--2.78 GiB peak working set because
  the offline evaluator holds the full dataset and multiple replays.  The
  transfer phase processed about 334--372 queries/s on this machine.

The risk-bound run took 511.8 seconds, exposing a quadratic threshold scan.
That scan has now been replaced by an equivalent sorted cumulative scan with
`O(N log N)` offline time.  The recorded exploratory run used pointwise 95%
bounds while selecting among many thresholds; the current code additionally
uses Bonferroni familywise control over all threshold operating points.  Both
changes must be rerun before any model freeze.  A history-size and
name-block-density scaling curve remains mandatory before the paper is
complete.

## Consequences for the next iteration

1. Keep selective veto as the main hypothesis; do not promote its current
   coefficients or threshold.
2. Treat all 2022/2023+ results as development from now on.  Do not reuse the
   opened fifth bucket as an independent certificate.
3. Reproduce an official public strong baseline under the same candidate and
   split contract.  Until this is done, no public-baseline superiority claim
   is permitted.
4. On public development data, replace pointwise logistic scoring with a
   group-aware LightGBM/LambdaMART candidate ranker plus a separate
   cost-sensitive NIL gate.  Compare it against the logistic gate with fixed
   candidates, feature ablation and complexity measurements; do not add a GNN
   without sufficient repeated-identity graph evidence.
5. Reserve the advisor's verified ISTINA blind labels for the final frozen
   paired comparison.  Service predictions may select disagreements for
   labeling but may not train the method as truth.
