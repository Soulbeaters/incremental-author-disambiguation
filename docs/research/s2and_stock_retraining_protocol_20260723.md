# Stock-S2AND in-domain retraining control

Date: 2026-07-23

## Purpose

The official S2AND v1.21 production bundle is an external frozen baseline.  A
second control retrains the unchanged official S2AND model family on the same
public Crossref--ORCID development domain.  This isolates gains caused by
ordinary domain adaptation and hyperparameter selection from gains caused by
Project Two's multilingual or open-set method.

Changing tree depth, leaf count, estimator count, learning rate, or the
agglomerative threshold is therefore **not** a Project Two contribution.

## Registered temporal roles

| Role | Years | Permitted use |
|---|---:|---|
| Train | through 2022 | Pairwise fitting |
| Validation | 2023 | Pairwise hyperparameter and clustering-threshold selection |
| Development test | 2024 | Frozen diagnostic only |
| Public comparison | 2025--2026 | Full pipeline comparison after model freeze |
| ISTINA blind test | held separately | Final claim only after code/protocol freeze |

The source paper, not an individual authorship row, determines the temporal
side.  No paper may cross two roles.  The model feature payload contains
structured author names, observed coauthors, affiliation, venue/journal, paper
text and real SPECTER2.  ORCID is used only to construct hashed cluster
membership labels.  It is absent from every feature row, as is the synthetic
`original_name` field.

## Fixed stock configuration

- official S2AND `ANDData`, `FeaturizationInfo`, `PairwiseModeler` and
  `Clusterer`;
- unchanged official feature set;
- the official reference-feature path remains enabled even though the public
  replay has no source-complete citation lists, so this signal is missing
  equally for every compared method rather than silently dropping a stock
  feature;
- a label-independent SHA-256 sample of 30% of complete name blocks, used to
  bound official Python preprocessing memory while retaining 155,104/12,620/
  19,888 unique train/validation/test pair opportunities;
- within-block pair sampling;
- 100,000 train, 10,000 validation and 10,000 development-test pairs;
- 25 official Hyperopt trials for the pairwise model;
- average-linkage clustering and 25 official trials for `eps`;
- Python backend, because the optional Rust wheel is not installed.

The runner writes no raw feature rows or source identities.  S2AND/Hyperopt
output goes to a run-local log instead of stdout:

```powershell
& 'tmp\s2and_py311_env\python.exe' `
  'experiments\run_s2and_stock_public_training.py' `
  --authors 'C:\istina\materia 材料\测试表单\crossref_authors.json' `
  --article-authors 'C:\istina\materia 材料\测试表单\crossref_article_authors_map.json' `
  --enrichment-dir 'runs\semantic_scholar_specter' `
  --s2and-repo 'C:\tmp\s2and-reference' `
  --s2and-cache 'tmp\s2and_stock_cache' `
  --run-dir 'runs\s2and_stock_public_2022_2023_2024' `
  --block-fraction 0.30
```

The saved `clusterer.pkl`, its SHA-256, the exact input hashes, split audit,
pairwise diagnostics and fitted parameters form the frozen control artifact.
It must then be evaluated on the identical 2025--2026 incremental replay used
by the official v1.21 and Project Two methods.
