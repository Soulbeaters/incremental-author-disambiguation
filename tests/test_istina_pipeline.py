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
            config=IstinaPipelineConfig(accept_threshold=100.0, reject_threshold=99.0),
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


if __name__ == "__main__":
    unittest.main()
