import json
import tempfile
import unittest
from pathlib import Path

from disambiguation_engine.decision_trace import DecisionTraceLogger
from disambiguation_engine.decision_types import Decision
from integrations.istina_disambiguation_client import IstinaDisambiguationClient
from integrations.istina_pipeline import (
    IstinaDisambiguationPipeline,
    IstinaPipelineConfig,
    build_istina_history_state,
)


def history_row(author_id, name, coauthors=None, **fields):
    return {
        "author_id": str(author_id),
        "name": name,
        "article_id": fields.pop("article_id", f"history-{author_id}"),
        "coauthors": list(coauthors or []),
        **fields,
    }


class FakeServiceClient:
    from_exported_author = staticmethod(IstinaDisambiguationClient.from_exported_author)

    def __init__(self, response):
        self.response = response
        self.calls = []

    def request_candidates(self, authors, man_id):
        authors = list(authors)
        self.calls.append((authors, man_id))
        return self.response


class IstinaPipelineTests(unittest.TestCase):
    def test_calibrated_rescue_is_disabled_by_default(self):
        self.assertFalse(IstinaPipelineConfig().enable_calibrated_candidate_rescue)

    def test_history_rebuild_preserves_external_ids_and_decision_order(self):
        history = [
            history_row("author-b", "Alex Smith", article_id="P1"),
            history_row("author-a", "Alex Smith", article_id="P2"),
        ]
        mention = {
            "article_id": "P3",
            "name": "Alex Smith",
            "lastname": "Smith",
            "firstname": "Alex",
            "coauthors": [],
        }

        pipelines = [
            IstinaDisambiguationPipeline.from_history_mentions(history)
            for _ in range(2)
        ]
        results = [pipeline.decide_mention(mention) for pipeline in pipelines]

        for pipeline in pipelines:
            self.assertEqual(
                pipeline.history_state.external_to_database_id,
                {"author-a": "author-a", "author-b": "author-b"},
            )
        self.assertEqual(results[0].topk, results[1].topk)
        self.assertEqual(results[0].author_id, results[1].author_id)
        self.assertEqual(results[0].deterministic_hash, results[1].deterministic_hash)

    def test_bounded_context_blocking_keys_use_stable_lexical_order(self):
        state = build_istina_history_state([
            history_row(
                "A1",
                "Alex Smith",
                article_id=f"P{index}",
                affiliation=affiliation,
                journal=journal,
            )
            for index, (affiliation, journal) in enumerate((
                ("Zeta University", "Zeta Journal"),
                ("Alpha University", "Alpha Journal"),
                ("Mu University", "Mu Journal"),
                ("Beta University", "Beta Journal"),
            ), start=1)
        ])

        keys = state.database.blocking_key_index
        self.assertIn("affil:alpha_university", keys)
        self.assertIn("affil:beta_university", keys)
        self.assertNotIn("affil:zeta_university", keys)
        self.assertIn("journal:alpha_journal", keys)
        self.assertIn("journal:beta_journal", keys)
        self.assertIn("journal:mu_journal", keys)
        self.assertNotIn("journal:zeta_journal", keys)

    def test_structured_surname_recovers_candidate_when_free_text_order_differs(self):
        state = build_istina_history_state([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Zhongyi Yu",
            "lastname": "Yu",
            "firstname": "Zhongyi",
            "coauthors": [],
        }])

        candidates = state.database.get_candidates({
            "name": "Yu Zhongyi",
            "surname": "Yu",
            "firstname": "Zhongyi",
        })

        self.assertEqual(
            [state.database_to_external_id[candidate.author_id] for candidate in candidates],
            ["A1"],
        )

    def test_blocking_normalizes_diacritics_without_changing_source_name(self):
        state = build_istina_history_state([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Pablo Pérez",
            "lastname": "Pérez",
            "firstname": "Pablo",
            "coauthors": [],
        }])

        candidates = state.database.get_candidates({
            "name": "P Perez",
            "surname": "Perez",
            "firstname": "P",
        })

        self.assertEqual(
            [state.database_to_external_id[candidate.author_id] for candidate in candidates],
            ["A1"],
        )

    def test_name_token_blocking_recovers_compound_surname_order(self):
        state = build_istina_history_state([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Ismael S. da Silva",
            "lastname": "Silva",
            "firstname": "Ismael S. da",
            "coauthors": [],
        }])

        candidates = state.database.get_candidates({
            "name": "da Silva, Ismael S.",
            "surname": "da Silva",
            "firstname": "Ismael S.",
        })

        self.assertEqual(
            [state.database_to_external_id[candidate.author_id] for candidate in candidates],
            ["A1"],
        )

    def test_exact_name_token_repair_merges_unique_informative_identity(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Ismael S. da Silva",
            "lastname": "Silva",
            "firstname": "Ismael S. da",
            "coauthors": [],
        }])

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "da Silva, Ismael S.",
            "lastname": "da Silva",
            "firstname": "Ismael S.",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "exact_name_token_repair")

    def test_high_risk_reordered_name_tokens_require_context(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Ming Li",
            "lastname": "Ming",
            "firstname": "Li",
            "coauthors": [],
        }])

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Li Ming",
            "lastname": "Li",
            "firstname": "Ming",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_blocking_folds_turkish_dotless_i(self):
        state = build_istina_history_state([{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Sönmez Fıratlı",
            "lastname": "Fıratlı",
            "firstname": "Sönmez",
            "coauthors": [],
        }])

        candidates = state.database.get_candidates({
            "name": "Sonmez Firatli",
            "surname": "Firatli",
            "firstname": "Sonmez",
        })

        self.assertEqual(
            [state.database_to_external_id[candidate.author_id] for candidate in candidates],
            ["A1"],
        )

    def test_structured_only_initial_candidate_cannot_directly_auto_merge(self):
        history = [
            {
                "gold_author_id": f"A{index}",
                "article_id": f"P{index}",
                "name": f"{initial} Kumar",
                "lastname": "Kumar",
                "firstname": initial,
                "coauthors": [f"C{index}"],
            }
            for index, initial in enumerate("ABCDE", start=1)
        ]
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=-100.0,
                reject_threshold=-200.0,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Kumar A.",
            "lastname": "Kumar",
            "firstname": "A",
            "coauthors": ["C1"],
        })

        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertEqual(result.stage, "enhanced_blocking_source_guard")

    def test_strict_full_structured_name_repairs_without_context(self):
        history = [{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "Hanna Viskari",
            "lastname": "Viskari",
            "firstname": "Hanna",
            "coauthors": [],
        }]
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )
        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Viskari, Hanna",
            "lastname": "Viskari",
            "firstname": "Hanna",
            "coauthors": [],
        })
        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "strict_structured_name_repair")

    def test_initial_only_name_is_not_strictly_repaired(self):
        history = [{
            "gold_author_id": "A1",
            "article_id": "P1",
            "name": "S Li",
            "lastname": "Li",
            "firstname": "S",
            "coauthors": [],
        }]
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )
        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "S. Li",
            "lastname": "Li",
            "firstname": "S",
            "coauthors": [],
        })
        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_short_family_with_informative_given_name_is_repaired(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "Ma Jiaxin", lastname="Ma", firstname="Jiaxin")],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Jiaxin Ma",
            "lastname": "Ma",
            "firstname": "Jiaxin",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "strict_structured_name_repair")

    def test_long_family_with_two_initials_is_repaired(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row(
                "A1",
                "Skurikhin A V",
                lastname="Skurikhin",
                firstname="A",
                middlename="V",
            )],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "A. V. Skurikhin",
            "lastname": "Skurikhin",
            "firstname": "A",
            "middlename": "V",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "strict_structured_name_repair")

    def test_initial_compatible_identity_blocks_strict_full_name_repair(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [
                history_row("A1", "Rui Zhang", lastname="Zhang", firstname="Rui"),
                history_row("A2", "R. Zhang", lastname="Zhang", firstname="R"),
            ],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Rui Zhang",
            "lastname": "Zhang",
            "firstname": "Rui",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_dense_exact_name_without_strong_context_is_not_auto_merged(self):
        history = [
            history_row("A1", "Yao Zhou", lastname="Zhou", firstname="Yao"),
            history_row("A2", "Bo Zhou", lastname="Zhou", firstname="Bo"),
            history_row("A3", "Li Zhou", lastname="Zhou", firstname="Li"),
            history_row("A4", "Min Zhou", lastname="Zhou", firstname="Min"),
            history_row("A5", "Qian Zhou", lastname="Zhou", firstname="Qian"),
        ]
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=-10.0,
                reject_threshold=-100.0,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Yao Zhou",
            "lastname": "Zhou",
            "firstname": "Yao",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertEqual(result.stage, "dense_name_block_context_guard")

    def test_history_state_quarantines_conflicting_identity(self):
        state = build_istina_history_state([
            history_row("10", "Peng Peng", lastname="Peng", firstname="Peng"),
            history_row("10", "Dawson Amanda", lastname="Dawson", firstname="Amanda"),
        ])

        self.assertEqual(state.quarantined_author_ids, frozenset({"10"}))
        self.assertIn("10", state.external_to_database_id)

    def test_local_merge_returns_external_istina_id(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row(
                "10",
                "Smith John",
                ["Brown A", "Green B"],
                lastname="Smith",
                firstname="John",
            )
        ])

        result = pipeline.decide_mention({
            "name": "Smith John",
            "lastname": "Smith",
            "firstname": "John",
            "article_id": "new",
            "coauthors": ["Brown A", "Green B"],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "10")
        self.assertEqual(result.stage, "local_fs")

    def test_structured_repair_recovers_local_new_with_context(self):
        config = IstinaPipelineConfig(accept_threshold=100.0, reject_threshold=99.0)
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row(
                "10",
                "Skurikhin A.",
                ["One A.", "Two B.", "Three C."],
                lastname="Skurikhin",
                firstname="A",
            )
        ], config=config)

        result = pipeline.decide_mention({
            "name": "Skurikhin A.V.",
            "lastname": "Skurikhin",
            "firstname": "A",
            "middlename": "V",
            "article_id": "new",
            "coauthors": ["One A.", "Two B.", "Other D."],
        })

        self.assertEqual(result.base_decision, Decision.NEW)
        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "10")
        self.assertEqual(result.stage, "structured_coauthor_repair")

    def test_initial_name_is_repaired_with_exact_affiliation_context(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row(
                "10",
                "Almira J M",
                lastname="Almira",
                firstname="J",
                middlename="M",
                affiliation="University of Granada",
            )
        ], config=IstinaPipelineConfig(
            accept_threshold=100.0,
            reject_threshold=99.0,
        ))

        result = pipeline.decide_mention({
            "name": "Jose M. Almira",
            "lastname": "Almira",
            "firstname": "Jose",
            "middlename": "M",
            "affiliation": "University of Granada",
            "article_id": "new",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "10")
        self.assertIn("affiliation", result.reason)

    def test_initial_name_without_independent_context_stays_unresolved(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row(
                "10",
                "Almira J M",
                lastname="Almira",
                firstname="J",
                middlename="M",
            )
        ], config=IstinaPipelineConfig(
            accept_threshold=100.0,
            reject_threshold=99.0,
            enable_unique_non_cjk_initial_repair=False,
        ))

        result = pipeline.decide_mention({
            "name": "Jose M. Almira",
            "lastname": "Almira",
            "firstname": "Jose",
            "middlename": "M",
            "article_id": "new",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_unique_non_cjk_initial_signature_is_repaired(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "J. M. Almira", lastname="Almira", firstname="J", middlename="M")],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=99.0,
                enable_unique_non_cjk_initial_repair=True,
            ),
            surname_risk_checker=lambda surname: surname in {"li", "qian", "zhang"},
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Jose Manuel Almira",
            "lastname": "Almira",
            "firstname": "Jose",
            "middlename": "Manuel",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "unique_non_cjk_initial_repair")

    def test_unique_local_surname_initial_does_not_merge_without_context_by_default(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("394890", "James A.", lastname="James", firstname="A")],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=99.0,
            ),
            surname_risk_checker=lambda _surname: False,
        )

        result = pipeline.decide_mention({
            "article_id": "future-paper",
            "name": "James Alexander",
            "lastname": "James",
            "firstname": "Alexander",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_unique_cjk_initial_signature_requires_context(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("A1", "C. Qian", lastname="Qian", firstname="C")],
            config=IstinaPipelineConfig(accept_threshold=100.0, reject_threshold=99.0),
            surname_risk_checker=lambda surname: surname in {"li", "qian", "zhang"},
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Chiping Qian",
            "lastname": "Qian",
            "firstname": "Chiping",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)

    def test_equal_name_without_context_is_not_repaired(self):
        config = IstinaPipelineConfig(accept_threshold=100.0, reject_threshold=99.0)
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row("10", "Chen Wei", lastname="Chen", firstname="Wei")
        ], config=config)

        result = pipeline.decide_mention({
            "name": "Chen Wei",
            "lastname": "Chen",
            "firstname": "Wei",
            "article_id": "new",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.NEW)
        self.assertIsNone(result.author_id)

    def test_strict_name_repair_cannot_bypass_dense_name_guard(self):
        history = [
            history_row(
                "A1",
                "Jun Zhang",
                lastname="Zhang",
                firstname="Jun",
            )
        ]
        history.extend(
            history_row(
                f"A{index}",
                f"Given{index} Zhang",
                lastname="Zhang",
                firstname=f"Given{index}",
            )
            for index in range(2, 7)
        )
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=-2.0,
                reject_threshold=-4.0,
            ),
        )

        result = pipeline.decide_mention({
            "name": "Jun Zhang",
            "lastname": "Zhang",
            "firstname": "Jun",
            "article_id": "new",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertEqual(result.stage, "dense_name_block_context_guard")
        self.assertIsNone(result.author_id)

    def test_dense_exact_name_can_use_independent_journal_context(self):
        history = [
            history_row(
                "A1",
                "Jun Zhang",
                lastname="Zhang",
                firstname="Jun",
                journal="Journal A",
            )
        ]
        history.extend(
            history_row(
                f"A{index}",
                f"Given{index} Zhang",
                lastname="Zhang",
                firstname=f"Given{index}",
            )
            for index in range(2, 7)
        )
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            history,
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
            ),
        )

        result = pipeline.decide_mention({
            "name": "Jun Zhang",
            "lastname": "Zhang",
            "firstname": "Jun",
            "article_id": "new",
            "journal": "Journal A",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "strict_structured_name_repair")

    def test_legacy_fallback_must_be_in_local_topk(self):
        config = IstinaPipelineConfig(accept_threshold=10.0, reject_threshold=-10.0)
        pipeline = IstinaDisambiguationPipeline.from_history_mentions([
            history_row("100", "Roberts C.", lastname="Roberts", firstname="C"),
            history_row("200", "Jones B.", lastname="Jones", firstname="B"),
        ], config=config)
        mention = {
            "name": "Roberts C.",
            "lastname": "Roberts",
            "firstname": "C",
            "article_id": "new",
            "coauthors": [],
        }

        accepted = pipeline.decide_mention(mention, service_response={
            "authors": [[{
                "id": 100,
                "last_name": "roberts",
                "first_name": "c",
                "middle_name": "",
                "name_similarity": 0.90,
            }]],
            "result_id": ["100"],
        })
        rejected = pipeline.decide_mention(mention, service_response={
            "authors": [[{
                "id": 200,
                "last_name": "jones",
                "first_name": "b",
                "middle_name": "",
                "name_similarity": 0.99,
            }]],
            "result_id": ["200"],
        })

        self.assertEqual(accepted.stage, "legacy_service_validated_fallback")
        self.assertEqual(accepted.author_id, "100")
        self.assertEqual(rejected.decision, Decision.UNKNOWN)
        self.assertNotEqual(rejected.author_id, "200")

    def test_paper_query_uses_short_family_guard_once(self):
        response = {
            "authors": [[{
                "id": 10,
                "last_name": "ма",
                "first_name": "цзясин",
                "middle_name": "",
                "name_similarity": 0.90,
            }]],
            "authors_names": [{"last_name": "ма", "first_name": "цзясин"}],
            "result_id": ["10"],
        }
        client = FakeServiceClient(response)
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row("10", "Ма Цзясин", lastname="Ма", firstname="Цзясин")],
            config=IstinaPipelineConfig(accept_threshold=10.0, reject_threshold=-10.0),
            service_client=client,
        )

        decisions = pipeline.decide_paper({
            "id": "paper",
            "authors": [{"lastname": "Ма", "firstname": "Цзясин"}],
        }, man_id=4705445, query_service=True, capture_legacy_shadow=True)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0][0].middle_name, "ч")
        self.assertEqual(decisions[0].legacy_result_id, "10")

    def test_final_pipeline_audit_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "trace.jsonl"
            logger = DecisionTraceLogger(
                trace_path=str(trace_path),
                salt="test-only-salt",
            )
            pipeline = IstinaDisambiguationPipeline.from_history_mentions(
                [history_row("10", "Sensitive Person", ["Coauthor A"])],
                trace_logger=logger,
            )
            result = pipeline.decide_mention({
                "name": "Sensitive Person",
                "lastname": "Sensitive",
                "firstname": "Person",
                "article_id": "new",
                "coauthors": ["Coauthor A"],
            }, audit_metadata={"article_id": "new"})

            raw = trace_path.read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertNotIn("Sensitive Person", raw)
            self.assertEqual(record["metadata"]["pipeline_stage"], result.stage)
            self.assertEqual(record["deterministic_hash"], result.deterministic_hash)

    def test_calibrated_rescue_exposes_frozen_model_audit_fields(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row(
                "A1",
                "Hanna Almira",
                lastname="Almira",
                firstname="Hanna",
            )],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
                enable_strict_name_repair=False,
                enable_exact_name_token_repair=False,
                enable_unique_non_cjk_initial_repair=False,
                enable_calibrated_candidate_rescue=True,
                calibrated_candidate_threshold=0.0,
                use_remote_fallback=False,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Hana Almira",
            "lastname": "Almira",
            "firstname": "Hana",
            "coauthors": [],
        })

        self.assertEqual(result.decision, Decision.MERGE)
        self.assertEqual(result.author_id, "A1")
        self.assertEqual(result.stage, "calibrated_candidate_rescue")
        self.assertGreater(result.calibrated_probability, 0.0)
        self.assertEqual(
            result.calibrated_model_version,
            "openalex-orcid-blind-logit-20260719-v2",
        )

    def test_calibrated_rescue_rejects_initial_only_name_without_context(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row(
                "A1",
                "Renata Cordeiro",
                lastname="Cordeiro",
                firstname="Renata",
            )],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
                enable_strict_name_repair=False,
                enable_exact_name_token_repair=False,
                enable_unique_non_cjk_initial_repair=False,
                enable_calibrated_candidate_rescue=True,
                calibrated_candidate_threshold=0.0,
                use_remote_fallback=False,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "R. Cordeiro",
            "lastname": "Cordeiro",
            "firstname": "R.",
            "coauthors": [],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)
        self.assertIsNone(result.author_id)

    def test_calibrated_rescue_cannot_override_incompatible_name(self):
        pipeline = IstinaDisambiguationPipeline.from_history_mentions(
            [history_row(
                "A1",
                "Kryukov Alexander",
                ["Shared Team"],
                lastname="Kryukov",
                firstname="Alexander",
            )],
            config=IstinaPipelineConfig(
                accept_threshold=100.0,
                reject_threshold=-100.0,
                enable_strict_name_repair=False,
                enable_exact_name_token_repair=False,
                enable_unique_non_cjk_initial_repair=False,
                enable_calibrated_candidate_rescue=True,
                calibrated_candidate_threshold=0.0,
                use_remote_fallback=False,
            ),
        )

        result = pipeline.decide_mention({
            "article_id": "P2",
            "name": "Volchugov Peter",
            "lastname": "Volchugov",
            "firstname": "Peter",
            "coauthors": ["Shared Team"],
        })

        self.assertNotEqual(result.decision, Decision.MERGE)
        self.assertIsNone(result.author_id)


if __name__ == "__main__":
    unittest.main()
