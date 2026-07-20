import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.istina_research_gate import assess_research_readiness, main


DATASET_SHA = "a" * 64


def framework_inputs():
    temporal = {
        "protocol": {
            "dataset_sha256": DATASET_SHA,
            "split_strategy": "temporal",
            "exact_duplicate_cleaning_applied": True,
            "framework_legacy_fallback_enabled": False,
            "legacy_service_observation_only": True,
        }
    }
    gold = {
        "production_temporal_split": {"paper_overlap": 0},
        "provenance": {"verified": False},
        "adjudication": {"unresolved": 2},
    }
    live = {
        "protocol": {
            "dataset_sha256": DATASET_SHA,
            "framework_legacy_fallback_enabled": False,
            "legacy_service_observation_only": True,
            "write_calls": 0,
        },
        "stats": {"authorized_commands": 0},
        "safety": {"no_write_authorized": True},
        "records": [
            {
                "article_id_hash": "paper-1",
                "runtime_correct": True,
                "legacy_correct": True,
            }
        ],
    }
    performance = {"summary": {"verified": True, "trial_count": 3}}
    paper = {
        "integrity": {"verified": True, "summary": {"failed": 0}},
        "quality_table": [
            {"source": "openalex_default"},
            {"source": "aminer_full_current"},
        ],
    }
    return temporal, gold, live, performance, paper


def passing_analysis():
    return {
        "verified": True,
        "population": {"paired_mentions": 2_000, "unique_papers": 120},
        "power_plan": {"effective_required_mentions": 1_960},
        "absolute_gain": 0.03,
        "mcnemar_exact_two_sided_p": 0.01,
        "cluster_randomization": {"p_value": 0.02},
        "cluster_bootstrap_gain_interval": {"lower": 0.005},
    }


class IstinaResearchGateTests(unittest.TestCase):
    def test_current_kind_of_evidence_can_be_framework_ready_without_claim(self):
        result = assess_research_readiness(*framework_inputs())

        self.assertTrue(
            result["framework_ready"], result["framework"]["failures"]
        )
        self.assertFalse(result["superiority_claim_ready"])
        self.assertFalse(result["writes_authorized"])
        failed = {
            item["name"] for item in result["superiority_claim"]["failures"]
        }
        self.assertIn("independently_verified_provenance", failed)
        self.assertIn("powered_paired_mentions", failed)

    def test_verified_powered_analysis_passes_claim_gate_but_never_writes(self):
        temporal, gold, live, performance, paper = framework_inputs()
        gold["provenance"]["verified"] = True
        gold["adjudication"]["unresolved"] = 0

        result = assess_research_readiness(
            temporal,
            gold,
            live,
            performance,
            paper,
            passing_analysis(),
        )

        self.assertTrue(result["framework_ready"])
        self.assertTrue(
            result["superiority_claim_ready"],
            result["superiority_claim"]["failures"],
        )
        self.assertFalse(result["writes_authorized"])

    def test_registered_plan_can_raise_the_required_sample(self):
        temporal, gold, live, performance, paper = framework_inputs()
        gold["provenance"]["verified"] = True
        gold["adjudication"]["unresolved"] = 0
        analysis = passing_analysis()
        analysis["power_plan"]["effective_required_mentions"] = 2_500

        result = assess_research_readiness(
            temporal, gold, live, performance, paper, analysis
        )

        self.assertFalse(result["superiority_claim_ready"])
        powered = next(
            item
            for item in result["superiority_claim"]["checks"]
            if item["name"] == "powered_paired_mentions"
        )
        self.assertEqual(powered["required"], ">=2500")

    def test_framework_gate_fails_on_comparator_leakage(self):
        temporal, gold, live, performance, paper = framework_inputs()
        temporal["protocol"]["framework_legacy_fallback_enabled"] = True

        result = assess_research_readiness(
            temporal, gold, live, performance, paper
        )

        self.assertFalse(result["framework_ready"])
        self.assertIn(
            "legacy_comparator_independence",
            {item["name"] for item in result["framework"]["failures"]},
        )

    def test_cli_writes_machine_readable_result(self):
        inputs = framework_inputs()
        names = ["temporal", "gold", "live", "performance", "paper"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, document in zip(names, inputs):
                path = root / f"{name}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                paths.append(path)
            output = root / "gate.json"
            with patch(
                "sys.argv",
                [
                    "istina_research_gate",
                    "--temporal-replay",
                    str(paths[0]),
                    "--gold-readiness",
                    str(paths[1]),
                    "--live-diagnostic",
                    str(paths[2]),
                    "--performance",
                    str(paths[3]),
                    "--paper-package",
                    str(paths[4]),
                    "--output",
                    str(output),
                ],
            ):
                main()

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(result["framework_ready"])
            self.assertFalse(result["superiority_claim_ready"])


if __name__ == "__main__":
    unittest.main()
