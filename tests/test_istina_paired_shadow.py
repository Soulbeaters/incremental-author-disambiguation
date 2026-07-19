import copy
import unittest

from evaluation.istina_paired_shadow import (
    PairedShadowCriteria,
    assess_paired_shadow,
    exact_mcnemar_two_sided,
    required_paired_mentions,
)


DATASET_SHA = "b" * 64
CODE_REVISION = "a" * 40


def criteria_for_test():
    return PairedShadowCriteria(
        absolute_min_mentions=40,
        min_unique_papers=10,
        min_expected_discordant_rate=0.10,
        min_bootstrap_iterations=100,
        min_randomization_iterations=100,
    )


def valid_plan():
    return {
        "schema_version": 1,
        "dataset_sha256": DATASET_SHA,
        "code_revision": CODE_REVISION,
        "registered_at": "2026-07-17T00:00:00+00:00",
        "registration_reference": "REG-123",
        "primary_endpoint": "paired known-author top-1 correctness",
        "alpha": 0.05,
        "power": 0.8,
        "minimum_absolute_gain": 0.5,
        "expected_discordant_rate": 1.0,
        "minimum_mentions": 40,
        "minimum_unique_papers": 10,
        "bootstrap_iterations": 100,
        "randomization_iterations": 100,
        "random_seed": 7,
        "maximum_analysis_looks": 1,
        "approval": {
            "approved_at": "2026-07-17T01:00:00+00:00",
            "reference": "STAT-456",
        },
    }


def valid_live_shadow():
    records = []
    for paper in range(10):
        for position in range(4):
            records.append({
                "article_id_hash": f"paper-{paper}",
                "position": str(position + 1),
                "runtime_correct": True,
                "legacy_correct": False,
                "legacy_result_present": True,
                "service_error": False,
            })
    return {
        "schema_version": 1,
        "generated_at": "2026-07-18T00:00:00+00:00",
        "protocol": {
            "dataset_sha256": DATASET_SHA,
            "code_revision": CODE_REVISION,
            "mode": "shadow",
            "write_calls": 0,
        },
        "stats": {
            "attempted_mentions": 40,
            "runtime_decisions": 40,
            "service_successful_mentions": 40,
            "legacy_result_present": 40,
            "service_errors": 0,
            "authorized_commands": 0,
        },
        "safety": {"no_write_authorized": True},
        "operational_evidence": {
            "online_shadow_verified": {"verified": True}
        },
        "records": records,
    }


class IstinaPairedShadowTests(unittest.TestCase):
    def assess(self, live=None, plan=None):
        return assess_paired_shadow(
            live or valid_live_shadow(),
            plan or valid_plan(),
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
            criteria=criteria_for_test(),
        )

    def test_power_formula_exceeds_500_for_default_two_percent_design(self):
        required = required_paired_mentions(
            alpha=0.05,
            power=0.8,
            minimum_absolute_gain=0.02,
            expected_discordant_rate=0.10,
        )

        self.assertEqual(required, 1960)

    def test_strong_preregistered_clustered_result_passes(self):
        result = self.assess()

        self.assertTrue(result["verified"])
        self.assertEqual(result["population"]["paired_mentions"], 40)
        self.assertEqual(result["population"]["unique_papers"], 10)
        self.assertEqual(result["summary"]["total"], 33)
        self.assertEqual(result["absolute_gain"], 1.0)
        self.assertLess(result["cluster_randomization"]["p_value"], 0.05)
        self.assertGreater(
            result["cluster_bootstrap_gain_interval"]["lower"], 0.0
        )
        self.assertFalse(result["privacy"]["mention_level_records_emitted"])

    def test_underpowered_result_fails_closed(self):
        plan = valid_plan()
        plan["minimum_mentions"] = 100

        result = self.assess(plan=plan)

        self.assertFalse(result["verified"])
        self.assertIn(
            "powered_mentions",
            {failure["name"] for failure in result["failures"]},
        )

    def test_duplicate_or_errored_pair_fails_closed(self):
        live = valid_live_shadow()
        live["records"][1] = copy.deepcopy(live["records"][0])
        live["records"][0]["service_error"] = True

        result = self.assess(live=live)

        self.assertFalse(result["verified"])
        self.assertIn(
            "record_format_and_uniqueness",
            {failure["name"] for failure in result["failures"]},
        )

    def test_malformed_nested_json_fails_without_crashing(self):
        live = valid_live_shadow()
        live["protocol"] = "not-an-object"
        live["records"] = {"not": "a-list"}

        result = self.assess(live=live)

        self.assertFalse(result["verified"])
        failures = {failure["name"] for failure in result["failures"]}
        self.assertIn("live_dataset_sha256", failures)
        self.assertIn("records_complete", failures)

    def test_plan_must_be_registered_before_live_run(self):
        plan = valid_plan()
        plan["registered_at"] = "2026-07-19T00:00:00+00:00"

        result = self.assess(plan=plan)

        self.assertFalse(result["verified"])
        self.assertIn(
            "registration_timestamp",
            {failure["name"] for failure in result["failures"]},
        )

    def test_mcnemar_is_symmetric_and_exact(self):
        self.assertEqual(exact_mcnemar_two_sided(0, 0), 1.0)
        self.assertAlmostEqual(
            exact_mcnemar_two_sided(10, 6),
            exact_mcnemar_two_sided(6, 10),
        )

    def test_excessive_resampling_request_fails_without_running_it(self):
        plan = valid_plan()
        plan["bootstrap_iterations"] = 10**12
        plan["randomization_iterations"] = 10**12

        result = self.assess(plan=plan)

        self.assertFalse(result["verified"])
        failures = {failure["name"] for failure in result["failures"]}
        self.assertIn("bootstrap_iterations", failures)
        self.assertIn("randomization_iterations", failures)


if __name__ == "__main__":
    unittest.main()
