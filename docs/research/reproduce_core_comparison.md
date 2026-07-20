# Reproduce the core comparison

The commands below write aggregate reports only. They do not write names, person IDs or mention-level records to the output.

```powershell
& 'C:\ProgramData\anaconda3\python.exe' experiments\compare_core_with_istina_proxy.py `
  --dataset '<crossref-orcid-author-records.json>' `
  --dataset-format crossref-orcid `
  --split-strategy temporal `
  --cutoff-year 2021 `
  --test-from-year 2023 `
  --project1-root '<project-one-root>' `
  --enable-calibrated-candidate-rescue `
  --calibrated-candidate-threshold 0.995 `
  --frozen-hybrid-policy unknown_or_new `
  --frozen-hybrid-threshold 0.5 `
  --frozen-native-graph-policy unknown_or_new `
  --frozen-native-graph-threshold 0.5 `
  --ablate-project2-evidence affiliation `
  --output '<aggregate-report.json>'
```

For the advisor ISTINA export, use `--dataset-format advisor-istina --split-strategy per-author-holdout`. The adapter constructs names only from structured family/given/middle fields. Records without a real identity label or usable structured name are excluded and counted in `protocol.adapter_summary`.

Use `--disable-project2-alias-index` only for the registered multi-alias
ablation; the frozen method keeps verified history aliases indexed.

The literature-guided topic/listwise ablation is intentionally separate from
the runtime.  It uses real Crossref title, abstract and venue fields, groups
all authorships from one paper into the same training fold, preserves the
frozen native graph threshold, and writes aggregate data only:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' experiments\evaluate_listwise_graph_gate.py `
  --dataset '<crossref-orcid-author-records.json>' `
  --crossref-raw '<crossref-work-responses.jsonl>' `
  --project1-root '<project-one-root>' `
  --train-paper-folds 5 `
  --preserve-native-threshold 0.5 `
  --max-unseen-false-rate 0 `
  --max-wrong-known 0 `
  --output '<aggregate-topic-gate-report.json>'
```

This is a reproducible Pareto/negative-result experiment, not a promoted
configuration.  See [literature_guided_algorithm_roadmap.md](literature_guided_algorithm_roadmap.md).

Run the focused tests with:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m pytest `
  tests\test_compare_core_with_istina_proxy.py `
  tests\test_paper_graph_rescue.py `
  tests\test_listwise_open_set_gate.py `
  tests\test_topic_profile_evidence.py -q
```
