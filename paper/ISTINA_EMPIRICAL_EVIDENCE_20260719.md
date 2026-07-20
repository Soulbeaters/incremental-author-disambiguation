# ISTINA author-disambiguation empirical evidence package

Package ID: `e94f328de56ca18c8d53f2e6b14f578a4a47d8264ee41bfbb30e09caff4b68a6`.

This package is internally consistent and machine-traceable for article use. It is not a write-enabled production authorization.

## Dataset and protocol status

- Advisor export SHA-256: `515c2d5881970f4de1a412d94018fa1aee99b5069956a1e139358bfc0de715fb`
- Frozen legacy sample SHA-256: `00d86db7994f5348d0b1805509ac2ad1a8be164b9eed59ea3721bea0635919b3`
- Exact duplicate author rows removed: 52
- Gold readiness: 4/12
- Verified ISTINA provenance: false
- OpenAlex confirmation SHA-256: `94a88f3fb1b14b5fd6596b04322f48081de0f3facefecc60c565bf1e366bced0`
- OpenAlex 10,000-work sample SHA-256: `39938f10c0707d42a19977488aaf9d7228f3b4c297e8fdaa9b035ae033e6cdcd`
- AMiner archive SHA-256: `d3912ea052afed43eeb401788312ab936055b02c2a52fd790c5c69e13db9defd`
- Retired runtime-validation source commit: `43b6b196b5a486f6ec5ab5df0e7c949b9805a668`

## Quality results

| Dataset | Protocol role | Test | Known | New | Paper overlap | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong-merge rate | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ISTINA advisor export | strict temporal primary | 571 | 5 | 566 | 0 | 0.00% | 0.00% | 94.22% | 5.08% | 0.00% | 12.96 |
| ISTINA advisor export | per-author diagnostic only | 1263 | 38 | 1225 | 13 | 100.00% | 71.05% | 95.88% | 3.33% | 0.00% | 1.34 |
| OpenAlex ORCID-blind confirmation | current-runtime public confirmation | 6232 | 3680 | 2552 | 0 | 100.00% | 71.93% | 78.90% | 16.13% | 0.00% | 8.23 |
| OpenAlex 10,000-work sample | current-runtime large cross-domain stress | 27430 | 552 | 26878 | 0 | 73.68% | 43.12% | 88.83% | 10.84% | 0.31% | 13.72 |
| AMiner KDD'18 test_100 | current-runtime complete public transfer stress | 6412 | 2744 | 3668 | 0 | 70.02% | 64.61% | 27.65% | 60.51% | 11.84% | 391.61 |

The OpenAlex and complete AMiner rows were rerun on the current runtime. All superseded ISTINA, OpenAlex, and AMiner result rows in `runtime_validation_20260719.json` are ignored.

## OpenAlex in-domain rescue ablation

| Configuration | Rescue enabled | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| production default | false | 100.00% | 71.93% | 78.90% | 16.13% | 0 | 8.23 |
| in-domain rescue ablation | true | 100.00% | 72.93% | 79.49% | 15.53% | 0 | 8.03 |

## OpenAlex 10,000-work cross-domain stress ablation

The complete-paper split contains 27,430 test mentions with zero publication overlap. This is public external validation, not ISTINA release evidence. The rescue result is retained as negative-transfer evidence.

| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| production default | false | 27430 | 73.68% | 43.12% | 88.83% | 10.84% | 85 | 13.72 |
| OpenAlex rescue ablation | true | 27430 | 48.90% | 48.37% | 88.93% | 10.03% | 279 | 12.28 |

## AMiner complete current-runtime cross-domain ablation

Both configurations use all 100 deterministic AMiner name blocks (6,412 test mentions) and zero publication overlap. The rescue run improves recall but causes lower precision and more wrong merges.

| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| production default | false | 6412 | 70.02% | 64.61% | 27.65% | 60.51% | 759 | 391.61 |
| OpenAlex rescue cross-domain ablation | true | 6412 | 63.03% | 73.14% | 31.30% | 50.34% | 1177 | 400.58 |

## AMiner bounded consistency ablation

This table uses the first 10 of 100 deterministic AMiner name blocks (679 test mentions). It is a bounded current-runtime ablation, not a replacement for the complete 6,412-mention current-runtime stress row.

| Configuration | Rescue enabled | Test | Merge precision | Known recall | Automatic accuracy | UNKNOWN | Wrong merges | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| production default | false | 679 | 72.28% | 66.67% | 30.34% | 58.03% | 79 | 376.28 |
| OpenAlex rescue cross-domain ablation | true | 679 | 61.85% | 80.26% | 36.52% | 40.94% | 153 | 301.91 |

## Fair legacy-service comparison

Framework decisions are computed with legacy-service fallback disabled; incumbent outputs are retained only as paired observations.

| Protocol | Shared cases | Framework correct | Legacy correct | Exact McNemar p | Significant at 0.05 |
|---|---:|---:|---:|---:|---:|
| strict temporal primary | 5 | 0 | 3 | 0.250000 | false |
| per-author diagnostic only | 38 | 27 | 24 | 0.629059 | false |
| per-author live diagnostic only | 38 | 27 | 24 | 0.629059 | false |

## Operational evidence

- Offline no-write operations: 13554
- Offline load p95: 14.67 ms
- Offline throughput: 295.15 mentions/s
- Deterministic mismatches: 0
- Runtime safety / rollback / drift fault tests: passed / passed / passed
- Real-service shadow: 5 mentions, 0 service errors, 0 authorized commands
- Live paper-request p95: 15205.50 ms
- Live audit chain verified / retained: true / false
- Real-service diagnostic replication: 38 mentions across 14 papers, framework 27 correct versus legacy 24 correct, 0 service errors, 0 authorized commands
- Diagnostic live paper-request p95: 14918.68 ms

## Article-safe interpretation

- The cleaned strict-temporal ISTINA sample has no observed wrong merge, but contains only 5 known-author cases and 0 automatic merges.
- The cleaned 38-case diagnostic compares the independent framework at 27 correct with the legacy service at 24 correct. A fresh read-only live run reproduces the same paired cells across 14 papers, but the exact paired test is not statistically significant.
- A five-mention real-service smoke demonstrates bounded no-write connectivity, not release-scale online performance.
- A separate 38-mention, 14-paper real-service diagnostic reproduces the frozen 27-versus-24 comparison with zero service errors and zero authorized commands; its overlapping per-author split and sub-threshold volume make it non-release evidence.
- The rescue improves recall without reducing precision on the current OpenAlex confirmation, but lowers precision and increases wrong merges on both the 27,430-mention OpenAlex stress ablation and the complete 6,412-mention AMiner ablation. Universal superiority is therefore unsupported.
- The current machine gate does not authorize write-enabled ISTINA replacement.

Claims that remain prohibited:

- statistically significant superiority over the legacy ISTINA service
- universal author-disambiguation superiority
- release-scale online latency or availability
- write-enabled production replacement authorization

## Machine release gate

Result: **8/23 passed; `release_ready: false`.**

| Missing check | Category | Observed | Required |
|---|---|---:|---|
| total_mentions | data | 571 | >=10000 |
| existing_mentions | data | 5 | >=1000 |
| new_mentions | data | 566 | >=1000 |
| shadow_mentions | data | 5 | >=500 |
| merge_precision | quality | 0 | >=0.995 |
| existing_recall | quality | 0 | >=0.95 |
| auto_accuracy | quality | 0.942207 | >=0.98 |
| unknown_rate | quality | 0.0507881 | <=0.02 |
| shadow_absolute_gain | comparison | -0.6 | >=0.02 |
| shadow_significance | comparison | 0.25 | <=0.05 |
| cross_domain_gold_verified | operations | false | validated gold from multiple ISTINA disciplines |
| online_shadow_verified | operations | false | live shadow run without writes |
| online_load_test_verified | operations | false | online end-to-end load and latency test |
| drift_monitoring_verified | operations | false | deployed data-quality and decision-drift monitoring |
| paired_shadow_analysis_verified | operations | false | pre-registered, adequately powered, paper-cluster-aware paired comparison against the legacy service |

## Source traceability

| Source | File | SHA-256 |
|---|---|---|
| aminer_default_current | `aminer_kdd18_test100_first10_default_current_20260719.json` | `edbf05a7c0985bbc5cad42171648b945087bc7d538d00eefa48b079637327f41` |
| aminer_full_current | `aminer_kdd18_test100_default_current_20260719.json` | `f8ef9434a15392b58086cbcb2bd19b339e237f626c3087edabeff0459b951246` |
| aminer_full_rescue_current | `aminer_kdd18_test100_rescue_current_20260719.json` | `c1c8be7ee0c6cb15a27a13fb0ec0b15c1f1252246cf2b4b0ad9912eff145502d` |
| aminer_rescue_current | `aminer_kdd18_test100_first10_rescue_current_20260719.json` | `6ca510c9d663d7ba5b23de75098e797bc441e621ba0215f5bb7688462c92f7e7` |
| bundle | `istina_release_evidence_bundle_20260719.json` | `5ef2405f4f0a1b4389dd8a456327ac7c6c8d19104de7fff5cb615eb995cc6ec3` |
| gate | `istina_production_gate_operational_20260719.json` | `adfbfab7ebc3d6a0a7cdd43784cf3c7c9c068fcae4d5692ba70092ce072cc8c8` |
| gold | `istina_gold_readiness_20260719.json` | `e337fbe9a9f8428353851d3b0626a5bc2ff3163856dca866db66c96972eea4ed` |
| holdout | `istina_holdout_runtime_replay_deduplicated_20260719.json` | `5006f00d7f8be4cb9ae5502bce9692b355a077a14a1511ee7cc9f41c624ad69d` |
| live | `istina_live_shadow_smoke_20260719.json` | `f3eb98ed8a0fbfdf5a199bd41a256ddc208cdfa8ff0965112eb59491666d2cf3` |
| live_diagnostic | `istina_live_shadow_diagnostic_20260719.json` | `82fa788f0c0285213752107608e2d3abc294c1817fb2eb8b5301f27d2c57358d` |
| openalex_default | `openalex_confirmation_default_current_20260719.json` | `038e9874ce9838e8e1153303f04164ccee5bd2c4b8cb2394725739006ae8e118` |
| openalex_large_default | `openalex_10000works_default_current_20260719.json` | `32ee0aab2ff41a85fba4069e9bb1479035ba366690d1e4d93fad6b20eb17dcc3` |
| openalex_large_rescue | `openalex_10000works_rescue_current_20260719.json` | `456b0ada4e05851597af19d028bde18b3af5dbeda912ce53c880a298f444d309` |
| openalex_rescue | `openalex_confirmation_rescue_ablation_current_20260719.json` | `12aeb53b945a4ad38d47850873b91b3c7aa7feda4a54c9dafe682427f41fe825` |
| operational | `istina_operational_validation_20260719.json` | `060e6ce6569f93e028c9ecae4116a9523bf96f74e99cbc3e168389403f308ae7` |
| public_validation | `runtime_validation_20260719.json` | `49ada917aac3084921df958e792593107e4f09c6f530c0c2c90d230659be01d2` |
| temporal | `istina_temporal_runtime_replay_20260719.json` | `7b7f0c305dc20634c598eb59302f6bf82663d19d293ab3e287bfc780e4485557` |
