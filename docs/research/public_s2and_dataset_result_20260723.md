# Paper-grade public S2AND development data — 2026-07-23

## Purpose and data role

This audit answers whether the existing public Crossref--ORCID material can
support a real official S2AND comparison.  It does **not** create an
independent test.  The public labels have already influenced Project Two and
remain development/transfer evidence only.  ORCID is a grouping label and is
never passed to either algorithm as a query feature.

All reports are aggregate-only.  Raw public metadata, DOI keys, names,
embeddings and batch responses remain under Git-ignored local `runs/` storage.
No advisor service prediction was used as a label.

## Local source audit

`crossref_authors.json` SHA-256:
`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`.

It contains:

- 301,586 author rows and 29,360 distinct DOI/article ids;
- 301,559 rows with structured first and last name;
- 150,797 rows with ORCID, 248,217 with year, and 117,745 with affiliation;
- zero author-position, full-paper-author, title, abstract, venue or journal
  fields; and
- a synthetic `original_name` field on every row, which all current adapters
  reject or delete before model construction.

The previously presumed raw `crossref.json` works file is actually a metadata
wrapper around another authors array.  It is not a source of paper metadata.

`crossref_article_authors_map.json` SHA-256:
`d72534f2053275833fbd6bc4ea14c8bf17ada73f0b95130c397e9a4b50260ba9`.

Its 31,502 article entries supply 410,724 author rows.  All 29,360 article ids
in the labelled export join successfully, covering every one of the 301,586
labelled rows.  The arrays recover complete coauthor context and source author
position; 409,832 map rows have structured `given/family` fields.

## Semantic Scholar enrichment

The official paper batch endpoint accepts up to 500 paper ids per request and
can return `embedding.specter_v2`.  The client uses deterministic DOI batches,
strictly serial requests, retry/backoff, atomic gzip caches and aggregate-only
stdout.  The full retrieval used 59 batches and no API key; no rate-limit or
server failure occurred.  The raw cache is private and approximately 185 MB.

| Signal | Papers | Coverage of 29,360 DOI |
|---|---:|---:|
| Semantic Scholar match | 25,344 | 86.32% |
| Title | 25,344 | 86.32% |
| Abstract | 20,259 | 69.00% |
| Venue/journal | 24,970 | 85.05% |
| Author list | 25,277 | 86.09% |
| SPECTER2 (768 dimensions) | 22,549 | 76.80% |

The missing 4,016 DOI records and 6,811 SPECTER2 vectors remain missing.  They
must not be fabricated or imputed when reporting the official baseline.

Primary API references: [Semantic Scholar paper batch API](https://api.semanticscholar.org/api-docs/),
[Semantic Scholar API tutorial](https://www.semanticscholar.org/product/api/tutorial),
and [Crossref REST guidance](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/).

## Strict S2AND-ready subset

Requiring all of the following—structured name, label-only ORCID, year, DOI,
complete paper-author context, and a real SPECTER2 vector—leaves:

- 108,905 labelled authorships;
- 20,329 papers;
- 39,759 distinct identities;
- 13,238 identities observed on at least two papers, covering 82,378
  authorships; and
- 7,333 identities observed on at least three papers.

Chronological open-set replay sizes are:

| History cutoff | History authorships | Query authorships | Known query | New query |
|---:|---:|---:|---:|---:|
| 2020 | 23,412 | 85,493 | 31,991 | 53,502 |
| 2021 | 35,776 | 73,129 | 31,209 | 41,920 |
| 2022 | 52,394 | 56,511 | 32,245 | 24,266 |

The 2021 cutoff is the existing public-development protocol and has ample
known and new-author cases for model training, ablation, learning curves,
complexity measurement, and an official baseline comparison.  It greatly
exceeds the minimum statistical sample sizes discussed for the eventual
ISTINA test, but it cannot replace domain-specific independent labels.

## Decision

Public sample size and missing coauthor context are no longer blockers.
Proceed with the official S2AND `0.51.1` / production-model `v1.21` adapter on
the 108,905-authorship subset, using the same history, query papers and hidden
labels as Project Two.  Report missing-data coverage before metrics.

Remaining gates are:

1. reproduce S2AND's required Python 3.11 environment and converter smoke test;
2. generate validated S2AND service-shaped JSON/Arrow artifacts without query
   ORCID or test labels in seeds;
3. run the paired public baseline and complexity audit; and
4. keep every result development-only until the separate verified ISTINA
   blind test is available.
