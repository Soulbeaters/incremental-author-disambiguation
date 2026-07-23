# PROJECT 2 — START HERE

## Canonical local home

**Use this directory for future Project 2 work:**

```text
C:\program 2 in 2025
```

This is the complete local project home. It contains the synchronized Git
repository plus private, Git-ignored research inputs and generated results that
do not exist in the Codex development copy.

Current scientific objective and irreversible data-split rules:

```text
PROJECT2_RESEARCH_GOAL.md
```

The machine-readable split contract starts from:

```text
config\research_data_split.template.json
```

Latest selective-risk algorithm experiment and complexity audit:

```text
docs\research\selective_risk_gate_result_20260722.md
```

Latest model-level grouped-ranker experiment:

```text
docs\research\grouped_ranker_result_20260722.md
```

Frozen official S2AND baseline and adapter contract:

```text
docs\research\s2and_official_baseline_adapter_audit_20260723.md
```

Current target algorithm and its no-regression contract:

```text
docs\research\s2and_ruzh_conditional_expert_20260723.md
```

Paper-grade public S2AND dataset audit and temporal split sizes:

```text
docs\research\public_s2and_dataset_result_20260723.md
```

GitHub research branch:

```text
https://github.com/Soulbeaters/incremental-author-disambiguation/tree/istina-risk-control-framework
```

Draft review PR:

```text
https://github.com/Soulbeaters/incremental-author-disambiguation/pull/1
```

## Copy roles

| Location | Role | Use |
|---|---|---|
| `C:\program 2 in 2025` | **Canonical local home** | Open, edit, test, commit and preserve private research material here |
| `C:\Users\mjx\Documents\Codex\project2-worktree` | Codex development copy | Temporary synchronized working copy used by Codex; not the complete local archive |
| GitHub branch | Public research source | Clean tracked source, tests, aggregate evidence and documentation only |

Both local Git copies must point to the same commit before handoff. The
canonical directory is authoritative because it also holds the ignored local
materials listed below.

## Private/local-only material in the canonical home

Do not commit or move these directories without checking their contents:

- `istina test/` — advisor-provided ISTINA export, including
  `chinese_articles_with_authors.json`;
- `results/` — historical and current generated experiment outputs;
- ignored files in `docs/` — paper PDFs, LaTeX sources and build products; and
- ignored generated OpenAlex rows in `data/`.

The versioned `evidence/` directory is different: it contains compact,
redacted aggregate evidence and hashes that are safe and necessary for
reproducibility.

## Future editing checklist

Open PowerShell and begin with:

```powershell
Set-Location 'C:\program 2 in 2025'
git status --short
git branch --show-current
git pull --ff-only origin istina-risk-control-framework
python -m pytest -q
```

Expected branch:

```text
istina-risk-control-framework
```

Before and after each future change:

1. keep private mention-level ISTINA data and raw service responses outside Git;
2. run the relevant tests and then the full test suite;
3. regenerate only the aggregate evidence affected by the change;
4. confirm `git status --short` is clean after commit; and
5. push the research branch and check the Python 3.10/3.11 GitHub jobs.

## Current scientific interpretation (23 July 2026)

The research framework and integration boundary are usable. The current
machine research gate reports `framework_ready: true` (9/9 checks) and
`superiority_claim_ready: false` (0/9 checks). The missing item is independent,
adequately powered ISTINA identity evidence—not a new standalone service.

Official S2AND is version-frozen and has been run on the same public temporal
protocol.  Stock retraining reduced new-author false links but lost 40 correct
known links, so it is a negative control and is not promoted.

The active method is now an official-S2AND fallback plus a conditional
Russian/Chinese expert.  Non-target output must be exactly unchanged.  The
expert can be promoted only if correct known links do not decrease,
wrong-known links do not increase, new-author false links do not increase, and
at least one outcome strictly improves.

Project One's Chinese surname/Pinyin/Palladius resources and an attributed
OpenCorpora Russian name-role lexicon are integrated as feature evidence, not
hard merge rules.  The current advisor export contains 279 target authorships
but only four repeated target identities; its post-2023 target test has zero
known cases.  It cannot establish target recall superiority.  A sufficiently
large verified target development set and the sealed ISTINA blind test remain
outstanding.

No current artifact authorizes writes to ISTINA.
