# Context and temporal-graph ablations — 2026-07-20

All choices below were made on the 2022 validation partition.  The 2023+ test
partition was not used to select a variant.

## Context evidence

| Project Two evidence removed | Known correct / 754 | New false links / 2,488 | B³ F1 | Pairwise F1 |
|---|---:|---:|---:|---:|
| None | 702 | 18 | 0.9497 | 0.6552 |
| Coauthor names | 701 | 7 | 0.9513 | 0.6657 |
| Affiliation strings | **705** | 7 | 0.9516 | 0.6687 |
| Both | 703 | **6** | **0.9516** | **0.6697** |

The selection rule maximizes known-author recall inside the false-link budget,
so raw affiliation strings are disabled and coauthor names are retained.

On the frozen 2023+ test this profile has 1,442/1,579 known authors correct,
one wrong known-author link and 39/10,241 unseen-author false links: 91.32%
known recall, 99.93% known-prediction precision and 0.38% unseen-author
false-link.  Relative to the non-ablated native profile it sacrifices two
correct known links and prevents fourteen unseen-author false links.

## Coauthor time decay

Five- and ten-year edge half-lives produce the same validation decisions as
the unweighted historical graph: 702 known authors correct, two wrong known
links and 18 unseen-author false links.  Time decay is therefore a neutral
ablation and is not enabled.

## Interpretation

Direct historical coauthor structure transfers; unnormalized affiliation text
does not.  Future affiliation evidence should use a verified institution ID or
a separately validated normalization layer rather than raw string overlap.
