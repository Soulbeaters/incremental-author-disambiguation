# Training-fixed threshold family and fixed-sequence risk calibration

Date: 2026-07-23

Status: opened public development result; certification failed; not an ISTINA
blind test

## Motivation

The previous gate formed a threshold family from every distinct score observed
on the 2021 selection split. This produced about 2,700 hypotheses and a
Bonferroni pointwise confidence near 99.998%. The procedure was label-safe but
converted useful ranker signal into excessive abstention.

The replacement follows the learn-then-test design:

1. fit the ranker and NIL gate on 2020 training data;
2. fix a conservative-to-liberal threshold family from 64 quantiles of the
   training gate scores, before opening 2021 selection labels;
3. test the ordered thresholds on selection at 95% confidence;
4. stop at the first threshold that fails either registered risk;
5. use the last passing threshold without changing it on certification or
   later comparison data.

This is based on the fixed-sequence testing construction in
[Learn then Test](https://people.eecs.berkeley.edu/~angelopoulos/publications/downloads/ltt.pdf)
and the independent calibration principle in
[Conformal Risk Control](https://proceedings.iclr.cc/paper_files/paper/2024/file/f3549ef9b5ff520a7e41ff3cc306ab2b-Paper-Conference.pdf).
The current implementation retains the existing one-sided binary-KL risk
bounds; it does not claim to be a complete conformal-risk-control algorithm.

## Frozen comparison

- Code revision: `f84276b`
- Same public replay, candidates, temporal roles and risk targets as the
  official S2AND comparison
- Requested training threshold grid: 64 quantiles
- Feature controls:
  - 28-dimensional non-semantic ranker/gate
  - 30-dimensional ranker/gate with paper-to-profile SPECTER cosine
- New-author false-link target: at most 0.5%
- Wrong-known target: at most 1.0%

Aggregate hashes:

- non-semantic exhaustive Bonferroni:
  `22796b20d00d680c28048491603a80f6e655b9276578d3f039f7914d586cb7ab`
- semantic exhaustive Bonferroni:
  `77c3beac359a937d316cd9dec8300bfb8a4f3b44b91d98e67d6cecbc90cbdfd0`
- non-semantic fixed sequence:
  `85ac66cd6702076fcc39ffdb6306713132f1800cce070c6f69506598abc8a6f3`
- semantic fixed sequence:
  `74f05f57550de07539f82868ac6acc55a688ecf06efdc55b09d2b8800edfa134`

## Two-factor ablation

| Feature/calibration | Selection coverage | Correct known | Wrong known | False links on new | Known recall | Known precision | New false-link rate | B³ F1 | Pairwise F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 28d + exhaustive Bonferroni | 27.63% | 11,439 | 6 | 27 | 44.89% | 99.948% | 0.0806% | 74.61% | 45.10% |
| Semantic + exhaustive Bonferroni | 19.82% | 8,338 | 6 | 20 | 32.72% | 99.928% | 0.0597% | 71.20% | 33.57% |
| 28d + fixed sequence | 33.75% | 14,349 | 9 | 46 | 56.31% | 99.937% | 0.1373% | 77.44% | 52.39% |
| Semantic + fixed sequence | 35.73% | 15,503 | 13 | 54 | 60.84% | 99.916% | 0.1612% | 78.42% | 54.42% |

The best development variant gains 4,064 correct known-author links and 15.95
recall points over the initial grouped gate while remaining below the
registered point risk targets. The interaction matters: the semantic feature
hurts under exhaustive Bonferroni but adds 1,154 correct known links and 4.53
recall points under fixed-sequence calibration.

For the semantic fixed-sequence variant:

- 46 distinct thresholds were realized from 64 requested quantiles;
- selection tested 25 thresholds before the first failure;
- selected threshold: 0.943387556086548;
- selection correct known: 3,178;
- selection wrong known: 4;
- selection false links on new: 9.

## Certification remains failed

All four variants use the same opened 2021 certification partition:

- new-author trials: 962
- best fixed-sequence semantic false links: 2
- observed new false-link rate: 0.208%
- one-sided 95% upper bound: 0.797%
- registered target: 0.5%
- statistical pass: no

The semantic fixed-sequence variant has zero wrong-known events on 1,163 known
queries, with a 0.257% upper bound, so the failure is specifically the
high-confidence new-author errors and the limited certification sample.

The 2022+ development comparison passes both risk bounds, but it has already
been opened repeatedly and cannot replace certification or an ISTINA blind
test.

## Relation to baselines

The current best risk-bounded variant still does not dominate the less
selective methods:

| Method | Known recall | New false-link rate | B³ F1 | Pairwise F1 |
|---|---:|---:|---:|---:|
| Project Two base | 76.38% | 1.570% | 82.13% | 64.35% |
| Project Two native graph | 86.95% | 2.173% | 85.10% | 72.56% |
| Semantic + fixed sequence | 60.84% | 0.161% | 78.42% | 54.42% |
| Official S2AND | 96.54% | 1.773% | 98.76% | 98.31% |

The contribution is a safer operating point with improved coverage, not broad
accuracy superiority.

## Complexity

The fixed-sequence threshold search reduces the hypothesis family from about
2,700 score-derived points to fewer than 50 realized training quantiles. Its
cost is negligible relative to candidate ranking. End-to-end wall time was:

- non-semantic fixed sequence: 509.21 seconds
- semantic fixed sequence: 675.02 seconds

Runtime variation includes warm filesystem caches, so these two runs are not a
standalone performance benchmark. Both remain practical for offline research.

## Decision and next step

Keep the semantic feature and fixed-sequence procedure as the current best
public-development branch, but do not promote or claim certification.

The unchanged two high-confidence new-author errors are now the binding
problem. More threshold search is unlikely to solve them without sacrificing
coverage. The next experiment must characterize these errors with
pseudonymized aggregate feature patterns and add temporally valid hard
negatives or an explicit veto feature. It must not inspect or tune on the
future ISTINA blind test.
