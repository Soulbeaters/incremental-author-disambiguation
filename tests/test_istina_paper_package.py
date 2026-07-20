import copy
import json
import unittest
from pathlib import Path

from evaluation.istina_paper_package import compose_paper_package, render_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT_ROOT / "evidence"


def load(name):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def source(name):
    import hashlib

    path = EVIDENCE / name
    return {"name": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def current_inputs():
    names = {
        "temporal": "istina_temporal_runtime_replay_20260719.json",
        "holdout": "istina_holdout_runtime_replay_deduplicated_20260719.json",
        "operational": "istina_operational_validation_20260719.json",
        "gold": "istina_gold_readiness_20260719.json",
        "live": "istina_live_shadow_smoke_20260719.json",
        "live_diagnostic": "istina_live_shadow_diagnostic_20260720.json",
        "online_canary": "istina_online_read_load_canary_20260720.json",
        "bundle": "istina_release_evidence_bundle_20260719.json",
        "gate": "istina_production_gate_operational_20260719.json",
        "openalex_default": "openalex_confirmation_default_current_20260719.json",
        "openalex_rescue": "openalex_confirmation_rescue_ablation_current_20260719.json",
        "openalex_large_default": "openalex_10000works_default_current_20260719.json",
        "openalex_large_rescue": "openalex_10000works_rescue_current_20260719.json",
        "aminer_full_current": "aminer_kdd18_test100_default_current_20260719.json",
        "aminer_full_rescue_current": "aminer_kdd18_test100_rescue_current_20260719.json",
        "aminer_default_current": "aminer_kdd18_test100_first10_default_current_20260719.json",
        "aminer_rescue_current": "aminer_kdd18_test100_first10_rescue_current_20260719.json",
        "public_validation": "runtime_validation_20260719.json",
    }
    documents = {key: load(name) for key, name in names.items()}
    documents["sources"] = {key: source(name) for key, name in names.items()}
    return documents


class IstinaPaperPackageTests(unittest.TestCase):
    def test_current_evidence_composes_verified_article_package(self):
        inputs = current_inputs()

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-19T00:00:00+00:00",
        )

        self.assertTrue(package["integrity"]["verified"])
        self.assertEqual(package["integrity"]["summary"]["total"], 67)
        self.assertFalse(package["release"]["release_ready"])
        self.assertEqual(package["quality_table"][0]["test_mentions"], 571)
        self.assertEqual(package["quality_table"][1]["paper_overlap"], 13)
        self.assertEqual(
            package["dataset_identity"]["retired_runtime_validation_source_commit"],
            "43b6b196b5a486f6ec5ab5df0e7c949b9805a668",
        )
        self.assertEqual(package["quality_table"][2]["test_mentions"], 6232)
        self.assertAlmostEqual(
            package["quality_table"][2]["existing_recall"],
            0.7192934782608695,
        )
        self.assertEqual(package["quality_table"][3]["test_mentions"], 27430)
        self.assertEqual(package["quality_table"][3]["paper_overlap"], 0)
        self.assertAlmostEqual(
            package["quality_table"][3]["merge_precision"],
            0.7368421052631579,
        )
        self.assertEqual(package["quality_table"][4]["wrong_merge_rate"], 759 / 6412)
        self.assertEqual(
            package["quality_table"][4]["source"],
            "aminer_full_current",
        )
        self.assertAlmostEqual(
            package["quality_table"][4]["p95_latency_ms"],
            391.6070999985095,
        )
        self.assertEqual(package["aminer_full_ablation_table"][0]["wrong_merge"], 759)
        self.assertEqual(package["aminer_full_ablation_table"][1]["wrong_merge"], 1177)
        self.assertEqual(package["aminer_current_ablation_table"][0]["wrong_merge"], 79)
        self.assertEqual(package["aminer_current_ablation_table"][1]["wrong_merge"], 153)
        self.assertEqual(package["legacy_comparison_table"][2]["n"], 38)
        self.assertEqual(
            package["legacy_comparison_table"][2]["paired_table"],
            {
                "both_correct": 20,
                "runtime_only_correct": 7,
                "legacy_only_correct": 7,
                "both_incorrect": 4,
            },
        )
        self.assertAlmostEqual(
            package["legacy_comparison_table"][2][
                "mcnemar_exact_two_sided_p"
            ],
            1.0,
        )
        self.assertEqual(
            package["legacy_service_drift"],
            {
                "observed": True,
                "framework_correct_frozen": 27,
                "framework_correct_current_live": 27,
                "legacy_correct_frozen": 24,
                "legacy_correct_current_live": 27,
                "legacy_correct_delta": 3,
                "paired_table_frozen": {
                    "both_correct": 17,
                    "runtime_only_correct": 10,
                    "legacy_only_correct": 7,
                    "both_incorrect": 4,
                },
                "paired_table_current_live": {
                    "both_correct": 20,
                    "runtime_only_correct": 7,
                    "legacy_only_correct": 7,
                    "both_incorrect": 4,
                },
                "current_live_generated_at": "2026-07-20T08:34:26.969760+00:00",
                "interpretation": (
                    "current incumbent observations differ from the frozen "
                    "comparison; report both and do not overwrite the frozen baseline"
                ),
            },
        )
        markdown = render_markdown(package)
        self.assertIn("7/23 passed", markdown)
        self.assertIn("legacy-service fallback disabled", markdown)
        self.assertIn("superseded", markdown)
        self.assertIn("OpenAlex in-domain rescue ablation", markdown)
        self.assertIn("OpenAlex 10,000-work cross-domain stress", markdown)
        self.assertIn("AMiner complete current-runtime", markdown)
        self.assertIn("Real-service diagnostic replication", markdown)
        self.assertIn("38 mentions across 14 papers", markdown)
        self.assertIn("Legacy-service result drift", markdown)
        self.assertIn("Online read-only load canary", markdown)
        self.assertEqual(
            package["operational_summary"]["online_canary_classification"],
            "bounded_non_release_canary",
        )
        self.assertFalse(package["operational_summary"]["offline_load_verified"])

    def test_user_canary_cannot_be_relabelled_as_release_evidence(self):
        inputs = current_inputs()
        online_canary = copy.deepcopy(inputs["online_canary"])
        online_canary["safety"]["verified"] = True
        online_canary["safety"]["institutional_approval"] = True
        online_canary["safety"]["evidence_classification"] = (
            "release_scale_online_load"
        )
        inputs["online_canary"] = online_canary

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-20T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "online_canary_remains_non_release",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )

    def test_live_diagnostic_framework_change_fails_closed(self):
        inputs = current_inputs()
        live_diagnostic = copy.deepcopy(inputs["live_diagnostic"])
        record = next(
            item
            for item in live_diagnostic["records"]
            if item["runtime_correct"] and not item["legacy_correct"]
        )
        record["runtime_correct"] = False
        live_diagnostic["stats"]["runtime_correct"] -= 1
        inputs["live_diagnostic"] = live_diagnostic

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-20T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "live_diagnostic_framework_matches_frozen_framework",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )

    def test_live_diagnostic_comparator_dependency_fails_closed(self):
        inputs = current_inputs()
        live_diagnostic = copy.deepcopy(inputs["live_diagnostic"])
        live_diagnostic["protocol"]["framework_legacy_fallback_enabled"] = True
        live_diagnostic["records"][0]["stage"] = (
            "legacy_service_validated_fallback"
        )
        live_diagnostic["records"][0]["name"] = "raw private name"
        inputs["live_diagnostic"] = live_diagnostic

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-19T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "legacy_comparator_independence",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )
        self.assertIn(
            "live_diagnostic_records_redacted",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )

    def test_large_public_ablation_hash_mismatch_fails_closed(self):
        inputs = current_inputs()
        rescue = copy.deepcopy(inputs["openalex_large_rescue"])
        rescue["protocol"]["dataset_sha256"] = "0" * 64
        inputs["openalex_large_rescue"] = rescue

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-19T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "openalex_large_dataset_sha256",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )

    def test_old_unsuperseded_istina_claim_fails_closed(self):
        inputs = current_inputs()
        public_validation = copy.deepcopy(inputs["public_validation"])
        public_validation.pop("artifact_status", None)
        public_validation["release_eligible"] = True
        public_validation["results"]["advisor_istina_default"] = {
            "test_mentions": 90,
        }
        inputs["public_validation"] = public_validation

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-19T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "superseded_public_source_guard",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )

    def test_cross_artifact_dataset_hash_mismatch_fails_closed(self):
        inputs = current_inputs()
        temporal = copy.deepcopy(inputs["temporal"])
        temporal["protocol"]["dataset_sha256"] = "f" * 64
        inputs["temporal"] = temporal

        package = compose_paper_package(
            **inputs,
            generated_at="2026-07-19T00:00:00+00:00",
        )

        self.assertFalse(package["integrity"]["verified"])
        self.assertIn(
            "single_dataset_sha256",
            {failure["name"] for failure in package["integrity"]["failures"]},
        )


if __name__ == "__main__":
    unittest.main()
