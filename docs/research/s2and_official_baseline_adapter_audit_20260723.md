# Official S2AND baseline adapter audit — 2026-07-23

## Decision

S2AND is a suitable strong public baseline for Project Two, but it must not be
reported from a name-only or zero-filled adapter.  The checked-in official
incremental model needs richer paper and cluster context than the current
author-only development export exposes directly.  The baseline is therefore
**specified but not yet scored**.

This is a data-contract limitation, not a reason to replace S2AND with a local
imitation.  The fair route is to enrich the same queries with source-observed
Crossref fields, construct history-only seed clusters, generate SPECTER2
vectors, and run both algorithms on the identical frozen query set.

## Frozen reference

- repository: AllenAI `S2AND` local reference clone;
- package version: `0.51.1`;
- source commit: `cb99b97c23a7c1bdbcb98cfe68abc6fec060c402`;
- production bundle: `production_model_v1.21`;
- pairwise source model: `v1.2`;
- incremental model family: `classic_lightgbm_linker`;
- retrieval: fixed top 25 candidate clusters;
- linker row: 53 features; and
- final gate: 240 inputs, promoted multiclass logistic calibration.

The bundle manifest and hashes must be copied into every result artifact.  A
later S2AND version is a separate baseline and must not silently replace this
one.

## Required fair input contract

| S2AND signal | Project Two source | State | Rule |
|---|---|---|---|
| structured first/middle/last name | author export | available | Never read `original_name` or an unstructured alias. |
| paper/signature id and author position | DOI/article id plus position | available | Keep every paper wholly within one split. |
| publication year | author export | available | Use source year only. |
| full paper author list/coauthors | grouped authorships | available | Build before filtering labeled target authors. |
| title | raw Crossref work record | enrichable | Join by normalized DOI; no inferred title. |
| venue/journal | raw Crossref work record | enrichable | Preserve missingness. |
| affiliation | author export | partial | Preserve missingness; do not fabricate. |
| SPECTER2 paper embedding | title/abstract through the official embedding route | missing | Required before a paper-grade score. Cache by DOI and record model/version/hash. |
| name-frequency counts | S2AND production resources | available | Use the bundle's declared semantics. |
| seed identity clusters | history labels only | constructible | Test-query labels must never enter seeds. |
| query ORCID | label-only field in the public export | prohibited | Blank it before inference for every method. ORCID may score results only. |

The Crossref--ORCID development export contains 120,815 usable authorships
(source file SHA-256
`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`).
It is large enough for adapter development, but all of its 2022 and 2023+
outcomes have already influenced Project Two and are not an independent final
test.

## Adapter invariants

1. Build a canonical paper table and authorship table once, with deterministic
   ordering and content hashes.
2. Delete and assert absence of `original_name` before constructing any model
   object.
3. Store ORCID/gold identity in a physically separate evaluation table.  The
   S2AND signature's query ORCID is always empty.
4. Form seed clusters only from the shared history partition.  Both S2AND and
   Project Two receive exactly the same profile history and query papers.
5. Never split coauthors from one paper across train, validation, or test.
6. Fail closed if required Arrow artifacts, seed inputs, DOI joins, or SPECTER2
   coverage do not meet the predeclared threshold.  Do not replace missing
   contextual features with fabricated values.
7. Save only aggregate diagnostics by default.  Per-person rows remain private
   and must never be printed to stdout.

## Evaluation protocol

### Public development

Use the existing chronological public partitions only for implementation,
error analysis, and model choice.  Report candidate recall separately from
link-or-NIL performance so retrieval and rejection errors are not conflated.
No public-development result is promotion-eligible.

### Verified ISTINA data

Before reading outcomes, freeze three roles:

- **train/history**: builds author profiles and may fit the Project Two ranker;
- **validation**: selects model structure and a single risk policy; and
- **sealed test**: opened once after code, thresholds, exclusions, and metric
  scripts are hashed.

Prefer a chronological split that represents deployment.  Keep complete
papers together, include both repeated and truly unseen identities, and
stratify the final report by name-block size, transliteration/script family,
profile size, missing context, and publication time.  Advisor services
`9091/9092/9093` are prediction baselines only; their outputs are never gold
labels or training targets.

## Shared measurements

For each method report:

- candidate coverage and known-author Top-1 recall;
- precision of accepted known links;
- false-link rate for genuinely new authors, with a one-sided confidence bound;
- wrong-existing-author rate, also with a confidence bound;
- abstention/NIL rate, B-cubed F1, and pairwise F1;
- paired query-level significance on the identical sealed cases; and
- wall time, CPU time, peak working set, throughput, model size, candidate
  count, and asymptotic inference cost.

The predeclared safety target remains a new-author false-link upper bound of
0.5% and a wrong-known-link upper bound of 1%, subject to adequate independent
sample size.  A method is not superior merely because it raises aggregate F1:
it must improve the agreed primary endpoint without violating either risk
bound.

## Next executable step

The leakage-safe intermediate payload builder and its in-memory tests are
implemented in `experiments/s2and_official_adapter.py`.  It requires complete
paper authors, source positions and 768-dimensional SPECTER2 vectors; it
rejects paper overlap and `original_name`, hashes history seed identifiers,
and never reads query labels.  A two-record parse through official `ANDData`
was attempted but stopped before construction because the current Python
environment lacks S2AND's `fasttext` dependency.  No package was installed in
the unattended session.  Reproduce the official environment from its locked
dependencies before the converter smoke test; do not monkeypatch preprocessing
or weaken the adapter to bypass this check.

After reproducing that environment, convert a tiny deterministic payload with
S2AND's official `convert_service_json_to_arrow` route, then run the same
streaming enrichment on the public development split with bounded logs.  Do
not score the baseline until SPECTER2 and DOI-join coverage are recorded and
all invariants pass.  The final comparison still waits for the independently
verified ISTINA split from the advisor.
