# Official S2AND public-development baseline — 2026-07-23

## Scope and reproducibility

This is a complete public-development run, not an ISTINA blind-test result.
The public ORCID labels have already influenced Project Two and cannot support
the final superiority claim.

- Project revision: `8019251ed3c2f35fce8e1b4a8cc87e821ccfae78`
- Official S2AND revision: `cb99b97c23a7c1bdbcb98cfe68abc6fec060c402`
- S2AND package: `0.51.1`
- Model bundle: `v1.21`, official Python pairwise plus exact incremental path
- Run signature: `46afa0fa8f6608dbaad3cf04646a44c2ba8641f3b92a9e29f954ebff073b1077`
- Aggregate-result SHA-256:
  `0ae63baa48cfb5fd9a7606e80fd0c50d6e6345f53a071e9e959d5bc195bcdd35`

The promoted Rust/Arrow incremental linker was not installed and is not
claimed. All 20,992 query-containing name blocks ran through the official
Python exact incremental method. SQLite contains exactly 20,992 anonymous
block checkpoints and the final aggregate is marked complete.

## Frozen replay

The leakage-safe join contains 32,761 history and 58,987 query authorships.
Only 24,444 history authorships occur inside a query-containing name block and
therefore enter S2AND feature computation; history from other blocks remains
part of the global known/new definition. The evaluation contains:

- 25,482 known-author queries;
- 33,505 genuinely new-author queries;
- 25,229 known queries with their gold identity inside the exact candidate
  block; and
- 1,336,512 theoretical pair comparisons after the strict position join.

Query ORCID is absent from every model row. History labels enter only as
opaque seed components. Article-map ORCID and the synthetic `original_name`
field are never read by the model adapter.

## Complete result

| Endpoint | Result | 95% Wilson interval |
|---|---:|---:|
| Candidate recall | 99.0071% | — |
| Known-author recall | 96.5387% | 96.3072–96.7563% |
| Precision among known-link predictions | 98.8428% | 98.7022–98.9684% |
| Precision among all accepted links | 96.5387% | 96.3072–96.7563% |
| Wrong-known rate | 1.1302% | 1.0076–1.2676% |
| New-author false-link rate | 1.7729% | 1.6370–1.9198% |

The underlying counts are:

- 24,600 correct known-author links;
- 288 wrong-existing-author links;
- 594 known-author NIL decisions;
- 594 false links for genuinely new authors; and
- zero seed-conflict queries.

Query-only clustering metrics, with queries linked to the same historical
identity unified across blocks, are:

| Metric | Precision | Recall | F1 |
|---|---:|---:|---:|
| B-cubed | 98.4898% | 99.0314% | 98.7599% |
| Pairwise | 98.1690% | 98.4418% | 98.3052% |

Pairwise counts are 254,405 true-positive pairs, 259,150 predicted pairs and
258,432 gold pairs.

## Complexity evidence

The complete invocation took 1,755.20 seconds wall time; summed block
inference time was 1,128.41 seconds. All 20,992 blocks reported exact Phase B.
The optional `psutil` package was absent from the isolated environment, so the
stored zero RSS value means **measurement unavailable**, not zero memory. No
peak-memory claim is made from this run; a later common harness must measure
both S2AND and Project Two consistently.

## Research implication

S2AND is a strong clustering and known-link baseline, but it fails both frozen
open-set risk targets: the new-author false-link rate is above 0.5%, and the
wrong-known rate is above 1%. Project Two should therefore not imitate its
aggressive operating point. The immediate comparison hypothesis is that a
candidate ranker plus an independently calibrated selective link/NIL gate can
reduce both error types while retaining materially more known-author recall
than a trivial abstention policy. The next experiment must use these exact
58,987 queries and report the recall sacrificed for each risk reduction.
