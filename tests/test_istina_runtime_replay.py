import unittest
from types import SimpleNamespace

from disambiguation_engine.decision_types import Decision
from experiments.istina_export_temporal_evaluation import mention_identity
from experiments.istina_runtime_replay import evaluate
from experiments.istina_operational_validation import drift_fault_injection
from integrations.istina_pipeline import IstinaPipelineDecision


class _Pipeline:
    def __init__(self):
        self.history_state = SimpleNamespace(
            external_to_database_id={"known": "db-known"}
        )

    def decide_mention(self, mention, service_response=None):
        gold = str(mention["gold_author_id"])
        decision = Decision.MERGE if gold == "known" else Decision.NEW
        return IstinaPipelineDecision(
            decision=decision,
            author_id=gold if decision == Decision.MERGE else None,
            stage="test",
            reason="test",
            base_decision=decision,
            local_score=1.0,
            candidate_count=1,
            scored_candidate_count=1,
            deterministic_hash=f"hash-{gold}",
        )


class IstinaRuntimeReplayTests(unittest.TestCase):
    def test_legacy_pairing_excludes_gold_not_seen_in_history(self):
        mentions = [
            {
                "article_index": 1,
                "article_id": "P1",
                "position": 1,
                "gold_author_id": "known",
                "name": "Known Author",
            },
            {
                "article_index": 2,
                "article_id": "P2",
                "position": 1,
                "gold_author_id": "new",
                "name": "New Author",
            },
        ]
        service_records = {
            mention_identity(mention): {"result_id": mention["gold_author_id"]}
            for mention in mentions
        }

        result = evaluate(_Pipeline(), mentions, service_records)

        self.assertEqual(result["stats"]["existing_gold"], 1)
        self.assertEqual(result["stats"]["new_gold"], 1)
        self.assertEqual(result["legacy_shadow"]["n"], 1)
        self.assertEqual(result["legacy_shadow"]["runtime_correct"], 1)
        self.assertEqual(result["legacy_shadow"]["legacy_correct"], 1)

    def test_drift_fault_injection_triggers_all_expected_alerts(self):
        decisions = [
            IstinaPipelineDecision(
                decision=Decision.NEW,
                author_id=None,
                stage="local_fs",
                reason="test",
                base_decision=Decision.NEW,
                local_score=-10.0,
                candidate_count=0,
                deterministic_hash=f"hash-{index}",
            )
            for index in range(100)
        ]

        result = drift_fault_injection(decisions)

        self.assertTrue(result["verified"])
        self.assertEqual(
            set(result["observed_alerts"]),
            set(result["expected_alerts"]),
        )


if __name__ == "__main__":
    unittest.main()
