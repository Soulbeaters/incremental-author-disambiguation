# Project Two research goal

## Scientific objective

Build a compact, reproducible incremental author-disambiguation method that
can be embedded into ISTINA and that improves the precision--recall--risk
frontier over the current ISTINA algorithms on independently verified labels.
The project is an algorithm study, not a replacement bibliographic service.

The main question is whether candidate ranking, paper-to-profile evidence and
selective open-set decisions can recover more known authors without exceeding
a preregistered false-link risk for genuinely new authors.

## Frozen RuZh conditional-expert contract

The research target is now narrower than global SOTA: improve author
disambiguation for Russian-script and Chinese-name records while preserving
the frozen official S2AND behavior elsewhere.  `RuZh` denotes a processing
stratum supported by source script and type-level name evidence; it is not an
ethnicity or nationality inference.

1. A target-independent router uses only observed structured first, middle and
   last fields, script inventory and frozen public/type-level lexicons.
2. Non-target records return the exact official-S2AND decision object.  A
   non-target disagreement is a machine-gate failure.
3. Target records may use the Project One Chinese surname--Pinyin--Palladius
   aliases, Russian given/surname/patronymic morphology, multilingual name
   views and the open-set gate.  Lexicons are features and risk signals, never
   hard identity merge rules.
4. A candidate is promoted only on the identical labelled target queries when
   (a) correct known links do not decrease, (b) wrong-known links do not
   increase, (c) false links to genuinely new authors do not increase, and
   (d) at least one of those three outcomes strictly improves.
5. A version that trades one error type for another, changes non-target
   output, or merely retunes parameters without a strict target improvement
   remains an internal negative result and cannot become the reported method.

The first traceable resources are frozen in
`disambiguation_engine/resources/ruzh_name_resources.manifest.json`.  Project
One contributes 462 Han surnames represented by 1,204 Han/Pinyin/Palladius/
variant aliases.  OpenCorpora contributes 29,482 type-level Russian name
lemmas: 9,171 surname, 12,818 given-name and 7,493 patronymic lemmas.  Neither
resource contains person identities or publication labels.

The current 90-paper ISTINA export cannot evaluate this promotion contract.
After structured-field-only exact de-duplication it contains 279 target
authorships and 200 labelled target authorships, but only four repeated target
identities.  With history through 2023, its 101 target test authorships are all
new and zero are known.  It can diagnose target new-author false links but
cannot measure target known-author recall or wrong-known links.  No target
superiority claim may be drawn from it.

## Frozen S2AND research ladder

Project Two now uses official S2AND `0.51.1` / production bundle `v1.21` as a
frozen external reference.  It must not be replaced by a weaker local
imitation.  Experiments keep four claims separate:

1. official S2AND, unchanged;
2. stock S2AND features retrained and tuned on development labels;
3. `S2AND-RuZh`, adding only prespecified native-script, Cyrillic--Latin,
   Han--Pinyin, Pinyin--Palladius, patronymic, name-order, initials and
   short-surname-risk features; and
4. `S2AND-RuZh-Open`, adding an independently calibrated selective LINK/NIL
   decision with finite-sample risk bounds.

Tree depth, leaf count, estimator count, learning rate and clustering-threshold
tuning belong to the stock retraining control.  They are not a methodological
contribution.  The multilingual views are probabilistic features, never hard
identity merge rules.

The frozen public ablation compares
`listwise_semantic_cross_profile` with
`listwise_multilingual_cross_profile`.  Candidate retrieval, temporal
train/validation/certification/comparison roles, risk-threshold procedure and
all non-name features remain identical.  A variant is stopped if it has no
stable held-out gain or imposes unreasonable runtime or memory cost.

That ablation completed at Project Two revision `9fa59e8`.  It supports the
multilingual name-view family as a public-development improvement to the
selective gate, but it does not validate the Cyrillic/Palladius/Han subgroup
features and does not establish overall superiority over official S2AND.  The
stock-S2AND retraining control is now fixed as: train through 2022, select
pairwise and clustering parameters on 2023, run a frozen development test on
2024, then compare the frozen pipeline on 2025--2026.  The next
domain-specific claim still requires verified ISTINA development labels.

The registered public pool contains 46,545 train, 13,698 validation and 16,083
development-test authorships after the same strict structured-name,
complete-coauthor and real-SPECTER2 join.  The memory-bounded official Python
control materializes a label-independent SHA-256 sample of 30% of complete
name blocks: 14,334/4,272/4,935 authorships and
155,104/12,620/19,888 unique within-block pair opportunities.  It still draws
the registered 100,000/10,000/10,000 pairs.  The public data's near-total
Latin-script coverage remains insufficient for a Russian--Chinese subgroup
claim.

The stock control has now completed.  On the full 2025--2026 public
comparison it reduces new-author false links from 265 to 188 and raises
accepted-link precision from 0.954413 to 0.962675, but loses 40 correct known
links (known recall 0.962943 to 0.958583).  B³ F1 rises by 0.001350 while
Pairwise F1 falls by 0.004940.  This is a changed risk--coverage trade-off, not
overall superiority.  The next algorithmic target is therefore the conditional
`S2AND-RuZh-Open` layer above.  It must preserve official S2AND outside the
target and pass the three-outcome target gate; Russian--Chinese gain claims
remain blocked on verified target-domain development labels with repeated
identities.

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
Its available cross-script labels are too sparse to validate a Palladius
claim.  That claim requires verified ISTINA development pairs or another
provenance-preserving public gold set.

The advisor's 9091/9092/9093 outputs are predictions.  They may be used as
baselines, candidate sources and disagreement-sampling signals, but never as
gold labels.  A disagreement becomes training data only after an independent
human or database label has been attached.

All model boundaries accept only source-observed structured name fields.
Synthetic or fabricated `original_name` values are prohibited for features,
blocking, training, calibration and evaluation.

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
2. Compare stock S2AND retraining with the Russian--Chinese feature family so
   that data/parameter adaptation cannot be mistaken for method novelty.
3. Improve hard-negative learning, paper-to-profile cross features, relation
   quality and cross-year calibration before increasing model depth.
4. Keep candidate retrieval separate from the MERGE/NEW/UNKNOWN decision and
   certify the final combined system, not only the added rescue gate.
5. Admit a GNN only when verified repeated identities and relations are large
   enough and the method contributes more than applying a standard GNN.
6. Report candidate Recall@K, Top-1, known recall/precision, wrong-known and
   new-author false-link rates, UNKNOWN, B3/Pairwise, calibration, risk bounds,
   paired inference, complexity, scalability, learning curves and ablations.

Every promoted method must also state asymptotic time and space cost, peak
working memory, end-to-end and per-query runtime, and a scaling curve over
history size and candidate-block density.  Online inference must remain
bounded by the retrieved candidate set; a full-author-catalog pairwise scan is
not an acceptable accuracy trade-off for ISTINA integration.

No superiority wording is allowed until the machine research gate validates a
frozen split manifest and the independent ISTINA comparison passes.
