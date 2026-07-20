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

Run the focused tests with:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m pytest `
  tests\test_compare_core_with_istina_proxy.py `
  tests\test_paper_graph_rescue.py -q
```
