# ISTINA author-disambiguation empirical evidence package

Package ID: `6b8f7c374c3510366eecc89e35d5b01374a97bbb334a7646bcc0aebddbd5cf1b`.

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
| ISTINA advisor export | strict temporal primary | 571 | 5 | 566 | 0 | 100.00% | 20.00% | 94.40% | 4.90% | 0.00% | 12.85 |
| ISTINA advisor export | per-author diagnostic only | 1263 | 38 | 1225 | 13 | 100.00% | 73.68% | 95.96% | 3.25% | 0.00% | 1.32 |
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

| Protocol | Shared cases | Framework correct | Legacy correct | Exact McNemar p | Significant at 0.05 |
|---|---:|---:|---:|---:|---:|
| strict temporal primary | 5 | 1 | 3 | 0.500000 | false |
| per-author diagnostic only | 38 | 28 | 24 | 0.454498 | false |

## Operational evidence

- Offline no-write operations: 13554
- Offline load p95: 21.42 ms
- Offline throughput: 199.21 mentions/s
- Deterministic mismatches: 0
- Runtime safety / rollback / drift fault tests: passed / passed / passed
- Real-service shadow: 5 mentions, 0 service errors, 0 authorized commands
- Live paper-request p95: 15462.99 ms
- Live audit chain verified / retained: true / false

## Article-safe interpretation

- The cleaned strict-temporal ISTINA sample has no observed wrong merge, but contains only five known-author cases and one merge.
- The cleaned 38-case diagnostic favors the framework 28 to 24, but the exact paired test is not statistically significant.
- A five-mention real-service smoke demonstrates bounded no-write connectivity, not release-scale online performance.
- The rescue improves recall without reducing precision on the current OpenAlex confirmation, but lowers precision and increases wrong merges on both the 27,430-mention OpenAlex stress ablation and the complete 6,412-mention AMiner ablation. Universal superiority is therefore unsupported.
- The current machine gate does not authorize write-enabled ISTINA replacement.

Claims that remain prohibited:

- statistically significant superiority over the legacy ISTINA service
- universal author-disambiguation superiority
- release-scale online latency or availability
- write-enabled production replacement authorization

## Machine release gate

Result: **8/21 passed; `release_ready: false`.**

| Missing check | Category | Observed | Required |
|---|---|---:|---|
| total_mentions | data | 571 | >=10000 |
| existing_mentions | data | 5 | >=1000 |
| new_mentions | data | 566 | >=1000 |
| shadow_mentions | data | 5 | >=500 |
| existing_recall | quality | 0.2 | >=0.95 |
| auto_accuracy | quality | 0.943958 | >=0.98 |
| unknown_rate | quality | 0.0490368 | <=0.02 |
| shadow_absolute_gain | comparison | -0.4 | >=0.02 |
| shadow_significance | comparison | 0.5 | <=0.05 |
| cross_domain_gold_verified | operations | false | validated gold from multiple ISTINA disciplines |
| online_shadow_verified | operations | false | live shadow run without writes |
| online_load_test_verified | operations | false | online end-to-end load and latency test |
| drift_monitoring_verified | operations | false | deployed data-quality and decision-drift monitoring |

## Source traceability

| Source | File | SHA-256 |
|---|---|---|
| aminer_default_current | `aminer_kdd18_test100_first10_default_current_20260719.json` | `edbf05a7c0985bbc5cad42171648b945087bc7d538d00eefa48b079637327f41` |
| aminer_full_current | `aminer_kdd18_test100_default_current_20260719.json` | `f8ef9434a15392b58086cbcb2bd19b339e237f626c3087edabeff0459b951246` |
| aminer_full_rescue_current | `aminer_kdd18_test100_rescue_current_20260719.json` | `c1c8be7ee0c6cb15a27a13fb0ec0b15c1f1252246cf2b4b0ad9912eff145502d` |
| aminer_rescue_current | `aminer_kdd18_test100_first10_rescue_current_20260719.json` | `6ca510c9d663d7ba5b23de75098e797bc441e621ba0215f5bb7688462c92f7e7` |
| bundle | `istina_release_evidence_bundle_20260719.json` | `98306a36bbb7b911ce65f20753c7de71cacb10e99df7a15a6d0607d1ecf09d8d` |
| gate | `istina_production_gate_operational_20260719.json` | `91cfd76f82598314e947928e503b14a7b15754ae99e3689c39de8020f0f493b5` |
| gold | `istina_gold_readiness_20260719.json` | `e337fbe9a9f8428353851d3b0626a5bc2ff3163856dca866db66c96972eea4ed` |
| holdout | `istina_holdout_runtime_replay_deduplicated_20260719.json` | `8d871d4d55b2442dd5336019179904e1ee9d2bb94f3982e9b69e94e5f4834185` |
| live | `istina_live_shadow_smoke_20260719.json` | `b0100dcab3c8f3229efbe7a0798063426999eb5f5c5fe14e0fe6d02e287ed595` |
| openalex_default | `openalex_confirmation_default_current_20260719.json` | `038e9874ce9838e8e1153303f04164ccee5bd2c4b8cb2394725739006ae8e118` |
| openalex_large_default | `openalex_10000works_default_current_20260719.json` | `32ee0aab2ff41a85fba4069e9bb1479035ba366690d1e4d93fad6b20eb17dcc3` |
| openalex_large_rescue | `openalex_10000works_rescue_current_20260719.json` | `456b0ada4e05851597af19d028bde18b3af5dbeda912ce53c880a298f444d309` |
| openalex_rescue | `openalex_confirmation_rescue_ablation_current_20260719.json` | `12aeb53b945a4ad38d47850873b91b3c7aa7feda4a54c9dafe682427f41fe825` |
| operational | `istina_operational_validation_20260719.json` | `a23a595b9414ea3ed668d385445b3fd1e4e902db89705e511c98969646fbd97e` |
| public_validation | `runtime_validation_20260719.json` | `49ada917aac3084921df958e792593107e4f09c6f530c0c2c90d230659be01d2` |
| temporal | `istina_temporal_runtime_replay_20260719.json` | `82df262deb595ec68af3f1420dec4eefe8dc3399ee9ad12dbbd52b066234c465` |
