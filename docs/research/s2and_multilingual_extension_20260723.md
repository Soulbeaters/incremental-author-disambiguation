# S2AND multilingual extension — 2026-07-23

## Research decision

Project Two will not rewrite or weaken the official S2AND baseline.  The
released S2AND `0.51.1` model at revision
`cb99b97c23a7c1bdbcb98cfe68abc6fec060c402` remains frozen as the external
reference.  Domain adaptation and multilingual method changes are separate
ablation rows:

1. official S2AND `v1.21`, unchanged;
2. stock S2AND features retrained on development labels;
3. stock features plus the Project Two multilingual name views; and
4. the multilingual ranker plus the independently calibrated open-set gate.

Tree depth, leaf count, estimator count and clustering threshold tuning belong
to row 2.  They are controls, not the paper's method contribution.

## Implemented feature boundary

`disambiguation_engine/multilingual_name_features.py` adds 14 deterministic
features without changing candidate identity labels:

- native-script family and given-name similarity;
- generic Latin-view family and given-name similarity;
- Pinyin/Palladius family and given-name similarity;
- initial compatibility and name-order swap compatibility;
- patronymic similarity plus an observedness mask;
- Cyrillic, Han and cross-script pair indicators; and
- an explicit short-family-name risk indicator.

The implementation accepts only structured first, middle and last fields.  It
fails closed if the prohibited unstructured synthetic field reaches this
boundary.  The feature output never contains a name, ORCID or identity value.

The Pinyin-to-Palladius resource contains 409 syllables extracted from the
five-page *Proposal to Add the Palladius Transcription to the Unihan
Database*.  Its source PDF SHA-256 is
`04a46ebcfb74b3b0cba0b6af75e85b4f00cf6b16f9d1e3018d5a2ef59ac3f625`;
the checked TSV SHA-256 is
`5689e565afdefb7bace8a3bfd5c996f6989acff4f80c92fdc36eea30efc37322`.
This makes `Ма Цзясин` and `Ma Jiaxing` a measurable cross-script feature
case rather than a one-off merge rule.

Primary references:

- [S2AND paper](https://arxiv.org/abs/2103.07534)
- [Official S2AND repository](https://github.com/allenai/S2AND)
- [Palladius/Unihan proposal](https://ponomar.net/files/palladius.pdf)
- [Reverse Palladius method](https://aclanthology.org/2012.amta-government.13/)

## Backward-compatible experiment integration

The features are appended to the existing grouped LightGBM ranker under the
new `listwise_multilingual_cross_profile` group.  The prior
`listwise_semantic_cross_profile` indices are unchanged, so it remains the
strict no-multilingual ablation.

New frozen bundles use `project2_lightgbm_bundle_v2`.  The loader maps legacy
`v1` bundle indices by stored feature name, including the NIL-gate summary
features whose absolute positions moved.  This preserves the previously
frozen Project Two evidence rather than invalidating it.

The first full ablation attempt reached the 20-minute process limit during
`comparison.rank`.  All corpus, training, validation, certification and
15,422-query comparison-evaluation phases had completed; the bottleneck was
recomputing identical profile-name views once per historical paper.  The
implementation now deduplicates a profile's structured names, caches only
deterministic per-string views, and skips the optional feature family for old
ablation groups.  This changes neither a feature value nor any statistical
protocol and is covered by a regression test.

## Real public-data coverage audit

The aggregate-only audit of the existing Crossref--ORCID source
(`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`)
found:

- 301,586 rows and 301,559 usable structured names;
- 301,448 Latin-only rows, 93 Cyrillic-only rows and 3 Han-plus-Latin rows;
- 96,634 rows with a high-risk East Asian romanized surname;
- 23,190 rows with a surname of at most two normalized characters;
- 45,730 labelled identities, but only 33 identities observed under different
  script signatures;
- 47 same-identity cross-script name pairs;
- 17 pairs rescued at similarity 0.95 by the generic Latin view; and
- zero labelled pairs that independently validate a Palladius rescue.

The audit reads ORCID only as a private grouping label and reports aggregate
counts.  It whitelists the three structured name fields and does not read any
unstructured name value.

## Consequence

The public data are large enough for the general S2AND retraining experiment,
the short-name risk analysis and Chinese romanized-name development.  They
are not large or diverse enough to claim that the Palladius feature improves
real Russian-written Chinese author disambiguation.

That claim requires either:

- verified ISTINA development records containing the same people under
  Cyrillic/Palladius and Pinyin/Han forms; or
- a separately sourced, provenance-preserving public gold subset.

The final ISTINA blind split remains sealed.  Advisor services remain
prediction baselines and cannot supply these labels.

## Next frozen ablation

On the existing temporal public-development protocol, run:

1. `listwise_semantic_cross_profile`; and
2. `listwise_multilingual_cross_profile`.

Use identical candidate sets, train/validation/certification years, fixed
sequence risk policy and final comparison queries.  Record feature importance,
known-author recall, new-author false-link rate, wrong-known rate, B-cubed,
pairwise F1, risk--coverage and runtime.  Do not promote the multilingual
family unless it improves a prespecified endpoint outside training without
violating either open-set risk bound.
