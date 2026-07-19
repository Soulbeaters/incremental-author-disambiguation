import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path

from evaluation.production_gate import ReleaseCriteria, assess_production_readiness


def passing_replay():
    return {
        "stats": {
            "total": 20_000,
            "existing_gold": 5_000,
            "new_gold": 15_000,
            "merge_for_new_gold": 1,
        },
        "metrics": {
            "precision": 0.999,
            "existing_recall": 0.97,
            "auto_accuracy": 0.995,
            "unknown_rate": 0.01,
            "wrong_merge_rate": 0.0001,
            "latency_ms_p95": 10.0,
        },
        "legacy_shadow": {
            "n": 1_000,
            "runtime_correct": 950,
            "legacy_correct": 850,
            "mcnemar_exact_two_sided_p": 0.001,
        },
    }


class ProductionGateTests(unittest.TestCase):
    def test_gate_passes_only_with_quality_and_operational_evidence(self):
        evidence = {
            "runtime_safety_contract_verified": True,
            "offline_load_test_verified": True,
            "cross_domain_gold_verified": True,
            "online_shadow_verified": True,
            "online_load_test_verified": True,
            "rollback_verified": True,
            "drift_monitor_test_verified": True,
            "drift_monitoring_verified": True,
            "paired_shadow_analysis_verified": True,
        }

        result = assess_production_readiness(passing_replay(), evidence=evidence)

        self.assertTrue(result["release_ready"])
        self.assertEqual(result["summary"]["failed"], 0)

    def test_gate_reports_sample_recall_and_operations_failures(self):
        replay = passing_replay()
        replay["stats"]["total"] = 1_264
        replay["stats"]["existing_gold"] = 90
        replay["metrics"]["existing_recall"] = 0.8777

        result = assess_production_readiness(replay)
        failed_names = {failure["name"] for failure in result["failures"]}

        self.assertFalse(result["release_ready"])
        self.assertIn("total_mentions", failed_names)
        self.assertIn("existing_recall", failed_names)
        self.assertIn("online_shadow_verified", failed_names)

    def test_gate_criteria_are_configurable(self):
        criteria = ReleaseCriteria(min_total_mentions=1)
        replay = passing_replay()
        replay["stats"]["total"] = 1
        evidence = {
            "runtime_safety_contract_verified": {"verified": True},
            "offline_load_test_verified": {"verified": True},
            "cross_domain_gold_verified": True,
            "online_shadow_verified": True,
            "online_load_test_verified": True,
            "rollback_verified": True,
            "drift_monitor_test_verified": {"verified": True},
            "drift_monitoring_verified": True,
            "paired_shadow_analysis_verified": True,
        }

        result = assess_production_readiness(replay, criteria, evidence)

        self.assertTrue(next(
            check["passed"] for check in result["checks"]
            if check["name"] == "total_mentions"
        ))

    def test_cli_accepts_operational_validation_artifact_as_evidence(self):
        from evaluation.production_gate import main

        evidence = {
            "operational_evidence": {
                "runtime_safety_contract_verified": {"verified": True},
                "offline_load_test_verified": {"verified": True},
                "cross_domain_gold_verified": {"verified": True},
                "online_shadow_verified": {"verified": True},
                "online_load_test_verified": {"verified": True},
                "rollback_verified": {"verified": True},
                "drift_monitor_test_verified": {"verified": True},
                "drift_monitoring_verified": {"verified": True},
                "paired_shadow_analysis_verified": {"verified": True},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay_path = root / "replay.json"
            evidence_path = root / "evidence.json"
            output_path = root / "gate.json"
            replay_path.write_text(json.dumps(passing_replay()), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            with patch("sys.argv", [
                "production_gate",
                "--replay-result", str(replay_path),
                "--evidence", str(evidence_path),
                "--output", str(output_path),
            ]):
                main()

            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(result["release_ready"])


if __name__ == "__main__":
    unittest.main()
