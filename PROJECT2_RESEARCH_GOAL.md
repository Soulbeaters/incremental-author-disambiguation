# Project Two research goal

## Scientific objective

Build a compact, reproducible incremental author-disambiguation method that
can be embedded into ISTINA and that improves the precision--recall--risk
frontier over the current ISTINA algorithms on independently verified labels.
The project is an algorithm study, not a replacement bibliographic service.

The main question is whether candidate ranking, paper-to-profile evidence and
selective open-set decisions can recover more known authors without exceeding
a preregistered false-link risk for genuinely new authors.

## Irreversible data roles

| Partition | Permitted use | Prohibited use |
|---|---|---|
| Public development data | Pretraining, algorithm development, ablation, public-baseline reproduction | Final ISTINA superiority claim |
| ISTINA train | Target-domain fitting and representation learning | Model selection or final reporting |
| ISTINA validation | Feature, model and threshold selection | Final reporting |
| ISTINA certification | Risk certification after threshold selection | Training the certified model |
| ISTINA blind test | One final paired comparison after all artifacts are frozen | Any training, calibration or redesign |

Crossref--ORCID 2023+ has already influenced development decisions.  It is a
development/transfer benchmark from now on, not an untouched test set.

The advisor's 9091/9092/9093 outputs are predictions.  They may be used as
baselines, candidate sources and disagreement-sampling signals, but never as
gold labels.  A disagreement becomes training data only after an independent
human or database label has been attached.

## Blind-test contract

Before any blind label is opened:

1. group records by paper and name block, then apply the registered temporal
   split;
2. prove zero record, paper and name-block overlap across development and
   blind-test partitions;
3. freeze the code commit, model artifact, feature schema, thresholds,
   candidate universe, service endpoints and evaluation protocol by SHA-256;
4. keep blind `person_id` labels with the advisor or another independent
   custodian; and
5. run Project Two, 9092, 9093 and public baselines on the same inputs.

If the algorithm is changed after blind results are seen, those results become
development evidence and a new blind test is required.

The target final test contains at least 1,000 known-author queries and 5,000
new-author or hard-negative queries.  Russian authors form the powered main
population; Chinese/transliterated names, initials, short surnames, common
surnames and dense same-name blocks are preregistered challenge strata.

## Algorithm and evidence priorities

1. Reproduce at least one official strong public baseline, preferably S2AND,
   S2APLER or WhoIsWho, under the same split and candidate contract.
2. Improve hard-negative learning, paper-to-profile cross features, relation
   quality and cross-year calibration before increasing model depth.
3. Keep candidate retrieval separate from the MERGE/NEW/UNKNOWN decision and
   certify the final combined system, not only the added rescue gate.
4. Admit a GNN only when verified repeated identities and relations are large
   enough and the method contributes more than applying a standard GNN.
5. Report candidate Recall@K, Top-1, known recall/precision, wrong-known and
   new-author false-link rates, UNKNOWN, B3/Pairwise, calibration, risk bounds,
   paired inference, complexity, scalability, learning curves and ablations.

No superiority wording is allowed until the machine research gate validates a
frozen split manifest and the independent ISTINA comparison passes.
