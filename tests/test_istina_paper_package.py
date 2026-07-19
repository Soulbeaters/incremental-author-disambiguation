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
        markdown = render_markdown(package)
        self.assertIn("8/21 passed", markdown)
        self.assertIn("superseded", markdown)
        self.assertIn("OpenAlex in-domain rescue ablation", markdown)
        self.assertIn("OpenAlex 10,000-work cross-domain stress", markdown)
        self.assertIn("AMiner complete current-runtime", markdown)

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
