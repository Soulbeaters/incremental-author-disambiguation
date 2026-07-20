# Incremental author disambiguation for ISTINA

> Local project location and editing guide:
> [`00_PROJECT2_START_HERE.md`](00_PROJECT2_START_HERE.md). The canonical local
> home is `C:\program 2 in 2025`; Codex copies are development mirrors.

Research framework for conservative, incremental author disambiguation and
evaluation against the current ISTINA candidate service. The intended outcome
is an algorithmic component that can be integrated into ISTINA, not a separate
replacement information system.

## Scope

| Layer | Status | Purpose |
|---|---|---|
| Research core | Active | Normalization, blocking, evidence scoring, `MERGE` / `NEW` / `UNKNOWN`, reproducible evaluation and ablations |
| ISTINA integration | Active | Read-only candidate lookup, fail-closed decision pipeline, audit-safe adapter contract |
| Deployment operations | Future optional | Load plans, release gate, monitoring, rollback and institutional handoff for a later ISTINA deployment |

The production-oriented files remain versioned because they may be useful when
ISTINA adopts the component. They are not requirements for demonstrating the
research method and are not being expanded into a standalone service.

## Current research status (20 July 2026)

- The framework, tests, deterministic replay, public-data validation and
  read-only ISTINA adapter are implemented.
- The article evidence package passes all 74 internal integrity checks.
- Three frozen-revision offline trials cover 40,662 operations; median/max p95
  latency is 6.67/7.29 ms with zero deterministic mismatches.
- A current-service diagnostic covers 38 known mentions in 14 papers. The
  framework and current service are both correct on 27/38; exact McNemar
  `p=1.0`. This does not establish superiority.
- The strict temporal advisor export contains 571 test mentions, but only five
  known-author cases. Its provenance is not independently adjudicated and two
  possible identity conflicts remain unresolved.
- ISTINA writes remain disabled. No current artifact authorizes writes.

The framework is usable for research experiments and integration development.
The missing item is sufficiently large, independently verified ISTINA evidence
for a statistically powered comparison with the incumbent service. Public
OpenAlex and AMiner experiments demonstrate transfer behaviour and negative
transfer risks, but cannot replace ISTINA identity labels.

See [research scope](docs/ISTINA_RESEARCH_SCOPE.md), the
[current status report](ISTINA_AUTHOR_DISAMBIGUATION_STATUS_20260719.md), and
the [empirical evidence package](paper/ISTINA_EMPIRICAL_EVIDENCE_20260719.md).

## Research questions

1. Can conservative multi-signal decisions reduce false identity links while
   preserving useful known-author recall?
2. Does the framework outperform the frozen/current ISTINA service on the same
   independently labelled future mentions?
3. How robust is it to short surnames, initials, transliteration variants and
   missing patronymics?
4. Which rules transfer across ISTINA, OpenAlex and AMiner, and where does
   negative transfer occur?
5. Are decisions reproducible and computationally suitable for embedding in
   the existing ISTINA pipeline?

## Architecture

```text
publication author mention
  -> normalization and script-aware name variants
  -> candidate retrieval (local history + optional read-only ISTINA service)
  -> multi-signal scoring and conservative thresholds
  -> MERGE | NEW | UNKNOWN
  -> redacted trace / evaluation evidence
```

The incumbent service is an observation-only comparator during fair
experiments. Its response must never be consumed as fallback evidence by the
framework arm being compared with it.

## Reproduce the checked evidence

Install Python 3.10 or 3.11 dependencies and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q

python evaluation/istina_research_gate.py `
  --temporal-replay evidence/istina_temporal_runtime_replay_20260719.json `
  --gold-readiness evidence/istina_gold_readiness_20260719.json `
  --live-diagnostic evidence/istina_live_shadow_diagnostic_20260720.json `
  --performance evidence/istina_offline_performance_reproducibility_20260720.json `
  --paper-package paper/istina_empirical_evidence_20260719.json
```

Private advisor exports, raw names, identity IDs, service responses and audit
logs must remain outside Git. Repository evidence contains aggregates, hashes
and redacted identifiers only.

## Repository map

- `disambiguation_engine/`: normalization, blocking, scoring and decision core.
- `integrations/`: ISTINA client, pipeline, safety contract and audit support.
- `experiments/`: deterministic offline and bounded read-only live runners.
- `evaluation/`: gold/provenance checks, paired inference, paper package and
  independent research/production gates.
- `evidence/`: redacted machine-readable aggregate evidence.
- `paper/`: article-ready tables and claim boundaries.
- `docs/ISTINA_RESEARCH_SCOPE.md`: active scientific protocol and completion
  criteria.
- `docs/ISTINA_PRODUCTION_RUNBOOK.md` and
  `docs/ISTINA_INSTITUTIONAL_HANDOFF.md`: deferred ISTINA deployment references.

## Interpreting the gates

`evaluation/istina_research_gate.py` reports two independent outcomes:

- `framework_ready`: implementation, leakage controls, comparator independence,
  reproducibility and evidence integrity are suitable for continued research.
- `superiority_claim_ready`: independent labels and a preregistered, adequately
  powered, paper-cluster-aware paired comparison support a superiority claim.

`evaluation/production_gate.py` is stricter and operational. It is retained for
a future institutional deployment decision. Neither gate grants write access;
write authorization belongs to ISTINA's institutional release process.

## License

MIT; see [LICENSE](LICENSE).
