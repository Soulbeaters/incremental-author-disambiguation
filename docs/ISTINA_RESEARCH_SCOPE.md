# ISTINA research scope and evidence protocol

## Decision

Project 2 is an embeddable author-disambiguation research framework for ISTINA.
It is not a new bibliographic platform and is not intended to replace ISTINA's
application, database, authentication, user interface or operations stack.

The active project has two required deliverables:

1. a reproducible algorithmic core that assigns conservative `MERGE`, `NEW` or
   `UNKNOWN` decisions from names and publication context; and
2. a minimal, read-only ISTINA integration boundary that demonstrates how the
   component can consume candidate results and return traceable decisions.

The load-test, paging, deployment-monitoring, rollback and write-authorization
materials are retained as future institutional adoption references. They do
not determine whether the research method or a correctly scoped article is
complete.

## Research questions and endpoints

| Question | Primary endpoint | Required evidence |
|---|---|---|
| Conservative identity assignment | Known-author recall, merge precision, unseen false-link rate, `UNKNOWN` rate | Strict temporal ISTINA evaluation with zero paper overlap |
| Improvement over ISTINA service | Paired top-1 correctness difference | Same independently labelled mentions for both arms; exact McNemar and paper-cluster-aware inference |
| Difficult-name robustness | Error rates by short surname, initials, missing patronymic and transliteration pattern | Prespecified ISTINA subgroups with enough cases to report uncertainty |
| Transfer and negative transfer | Precision/recall and wrong merges across corpora | Current-runtime OpenAlex and AMiner replays and ablations |
| Reproducibility and efficiency | Deterministic hashes and local p95 latency | At least three frozen-revision offline trials |

The incumbent result is observation-only in paired experiments. Framework
decisions must be produced with legacy fallback disabled.

## Evidence tiers

### 1. Framework readiness

The implementation is research-ready when all of the following are
machine-verifiable:

- the primary ISTINA split is temporal and has zero publication overlap;
- exact within-paper duplicate cleaning is recorded;
- the framework arm is independent of the incumbent comparator;
- no writes or authorized write commands occur;
- the paper package is internally consistent;
- public OpenAlex and AMiner transfer results are present; and
- at least three frozen-revision performance trials pass.

This tier supports continued experimentation and article claims that are
explicitly limited to the observed samples. It does not establish superiority.

### 2. Superiority-claim readiness

A claim that the framework improves on the current/frozen ISTINA service also
requires:

- independently audited ISTINA person-identity labels with documented export
  time and semantics;
- zero unresolved label conflicts;
- a plan registered before outcomes are observed;
- the plan's powered paired sample, never below the current 1,960-mention base
  design and 100 distinct papers;
- an observed absolute correctness gain of at least two percentage points;
- exact two-sided McNemar `p <= 0.05`;
- paper-cluster sign-flip `p <= 0.05`; and
- a paper-cluster bootstrap interval whose lower bound is above zero.

The 1,960 base follows the registered assumptions of two-sided `alpha=0.05`,
80% power, a two-point minimum gain and 10% expected discordance. A
statistician-approved cluster design effect may increase the final target.

If the final research question is changed from superiority to descriptive
feasibility, the claim and power analysis must be changed prospectively rather
than lowering the gate after seeing results.

## What current evidence establishes

- The research framework and integration boundary exist and are testable.
- The 74-check article package is internally consistent.
- Offline performance is repeatable across three frozen-revision trials.
- Public validation reveals useful in-domain behaviour and real negative
  transfer risk across datasets.
- The advisor service is reachable in bounded, read-only runs, including the
  known short-surname/patronymic edge case.
- The current 38-case comparison is diagnostic: both the framework and current
  service score 27/38, with McNemar `p=1.0`.

It does not establish that the framework is statistically superior to the
incumbent service. The strict temporal export has only five known-author cases;
service `result_id` values are model predictions, not independent truth.

## Minimal additional ISTINA evidence

Before requesting anything new, use all available advisor-export cases and
service observations. A separate request is necessary only if the existing
service cannot provide independently verified ground-truth identity labels and
enough paired known-author cases.

For the superiority study, request the following privacy-safe export:

- publication ID, publication year and author position;
- independently verified ISTINA person ID for each labelled mention;
- author name components and co-author identities/names;
- discipline, affiliation, journal and ORCID when available;
- export timestamp, identity-label semantics and audit/adjudication status; and
- the frozen incumbent result for the same future mentions, if it cannot be
  reproduced later.

The preferred first target is 1,960 or more labelled known-author mentions
across at least 100 papers; any smaller available tranche is still useful for
pilot error analysis but cannot by itself support the planned superiority
claim. Raw private rows must not be committed to Git.

## Deferred institutional deployment work

The following remain implemented or documented but are not active research
completion criteria:

- release-scale online load and availability testing;
- deployed paging and drift-monitor observation windows;
- durable audit retention and multi-worker operational evidence;
- candidate/write rollout, authorization and rollback; and
- the 23-check production release gate.

They become relevant only if ISTINA chooses a staging or production adoption
exercise, or if an article explicitly makes online service-level claims.
