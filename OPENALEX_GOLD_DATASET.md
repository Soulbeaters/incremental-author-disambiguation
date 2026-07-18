# OpenAlex author-disambiguation datasets

The project uses two reproducible OpenAlex protocols. They answer different
questions and must not be mixed in one accuracy claim.

## Random-work stress set

`data/build_openalex_gold.py` samples complete works and uses OpenAlex author
IDs as weak identity labels. It is useful for blocking, scale, and cold-start
stress tests, but OpenAlex author clusters can contain fragmentation or
placeholder identities. It is not treated as human-verified gold.

```powershell
python -X utf8 data\build_openalex_gold.py `
  --sample-works 10000 --seed 20260718 `
  --from-year 2010 --to-year 2025
```

## ORCID-labelled, ORCID-blind benchmark

`data/build_openalex_orcid_benchmark.py` samples OpenAlex author profiles with
ORCID, requests their works, and retains an authorship only when the embedded
authorship ORCID equals the profile ORCID. ORCID is written only to
`gold_author_id`; the runtime `orcid` field is blank. The model therefore never
receives the evaluation identity.

```powershell
python data\build_openalex_orcid_benchmark.py `
  --target-authors 2500 --sample-authors 3600 --seed 20260720 `
  --min-works 3 --max-works 5 --from-year 2000 --to-year 2025 `
  --workers 16 --output data\openalex_orcid_blind_mentions.jsonl `
  --metadata data\openalex_orcid_blind_metadata.json

python experiments\openalex_runtime_replay.py `
  --dataset data\openalex_orcid_blind_mentions.jsonl `
  --metadata data\openalex_orcid_blind_metadata.json `
  --split-strategy orcid-author-holdout `
  --history-papers-per-known-author 1
```

The deterministic split assigns about two thirds of identities to the known
author population. The first chronological paper of each known anchor goes to
history; all remaining complete papers go to test. The other third remain
unseen authors. No publication may occur on both sides. Two- and three-history
paper variants are supported for maturity analysis, but are reported
separately from the one-paper cold-start protocol.

Generated JSONL and metadata files are ignored by Git. Fixed seeds, request
parameters, source URLs, metadata counts, and builders are versioned so every
sample can be rebuilt without redistributing a large OpenAlex extract.

## Sources

- OpenAlex API and filtering documentation:
  <https://developers.openalex.org/>
- OpenAlex dataset paper: Priem, Piwowar, and Orr, “OpenAlex: A fully-open
  index of scholarly works, authors, venues, institutions, and concepts,”
  *Scientific Data* 9, 2022. <https://doi.org/10.1038/s41597-022-01371-4>
- ORCID identifier service: <https://orcid.org/>

OpenAlex display-name splitting is recorded as a heuristic input field, not as
a gold name-order annotation. Identity claims in reports must state whether
the label is weak OpenAlex clustering or ORCID equality.
