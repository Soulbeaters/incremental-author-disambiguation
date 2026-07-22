# Independent risk-calibration result — 2026-07-22

## Purpose

This experiment tests a method change, not a production deployment: threshold
selection and risk certification are separated by deterministic paper groups.
A one-sided finite-sample binary-KL bound is evaluated only after the feature
family and threshold have been frozen.  The 2023+ partition remains
confirmatory and is not used to tune the gate.

The source is the local real Crossref author export with SHA-256
`3546bcf7fa3566ab5ddc7105829c28df890e34544700034c70efbe2af7639806`.
The loader keeps structured given/family fields, paper/DOI, year and the ORCID
label, and removes the prohibited synthetic display field before constructing
model objects.  Affiliation was ablated.  No mention-level data is emitted.

## Scale and protocol

- Training: 24,961 history mentions through 2020 and 13,519 queries in 2021.
- Validation selection: 38,480 history mentions and 15,162 queries in four
  paper-hash buckets from 2022.
- Independent certification: 3,346 queries in the untouched fifth paper bucket.
- Confirmatory test: 63,827 mentions from 2023 onward.
- Training proposals: 1,163; selected family: 18-feature listwise gate without
  topic metadata; frozen threshold: `0.8372505258077464`.
- End-to-end wall time in this environment: approximately 550 seconds; the
  first instrumented rerun will record wall and CPU time inside the report.

## Independent certificate

| Risk | Observed | One-sided 95% upper bound | Target | Result |
|---|---:|---:|---:|---|
| New-author false link | 20 / 1,306 = 1.531% | 2.516% | 0.5% | fail |
| Wrong known-author link | 10 / 2,040 = 0.490% | 0.971% | 1.0% | pass |

The combined model is therefore **not eligible for promotion**.  The failure
comes from the final combined system, not merely the new gate additions; a
safe residual gate cannot certify an unsafe inherited base/native decision.

## Frozen 2023+ comparison

| Method | Known recall | Known-prediction precision | New-author false-link |
|---|---:|---:|---:|
| Native graph at 0.5 | 84.93% | 99.415% | 1.5626% |
| Selected listwise gate | 86.50% | 99.425% | 1.5679% |

The layered gate adds 414 correct known-author links and never removes a
native correct link, but it adds two new-author false links.  This is a useful
Pareto improvement, not a dominance result.  It also shows that the next
optimization target is the inherited native/base false-link risk and
cross-year calibration, not a deeper classifier alone.

These numbers are not directly comparable to the earlier 19,180-mention
curated transfer experiment because the source population and scale differ.
They must not be used to claim superiority over the live 9092/9093 services or
over ISTINA without independent person-ID labels.
