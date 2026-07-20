import copy
import unittest
from datetime import datetime, timezone

from evaluation.istina_online_load_plan import (
    ONLINE_LOAD_MODE,
    ONLINE_LOAD_PURPOSE,
    assess_online_load_plan,
    man_id_sha256,
    sha256_text,
)


DATASET_SHA = "b" * 64
CODE_REVISION = "a" * 40
SERVICE_URL = "http://93.180.23.185:9091/"
MAN_ID = 4705445
CHANGE_REFERENCE = "OPS-LOAD-123"
ACTIVE_TIME = datetime(2026, 7, 20, 10, 30, tzinfo=timezone.utc)


def valid_plan():
    return {
        "schema_version": 1,
        "source_system": "istina",
        "purpose": ONLINE_LOAD_PURPOSE,
        "mode": ONLINE_LOAD_MODE,
        "plan_id": "istina-load-20260720-01",
        "dataset_sha256": DATASET_SHA,
        "code_revision": CODE_REVISION,
        "service_url_sha256": sha256_text(SERVICE_URL),
        "man_id_sha256": man_id_sha256(MAN_ID),
        "requests": 1000,
        "concurrency": 4,
        "max_rps": 2.0,
        "service_timeout_seconds": 30.0,
        "window": {
            "start": "2026-07-20T10:00:00+00:00",
            "end": "2026-07-20T12:00:00+00:00",
        },
        "approval": {
            "scope": "institutional_load_window",
            "approved": True,
            "approved_at": "2026-07-20T09:00:00+00:00",
            "change_reference": CHANGE_REFERENCE,
            "approver_role": "service_owner",
        },
    }


def assess(plan, **overrides):
    arguments = {
        "expected_dataset_sha256": DATASET_SHA,
        "expected_code_revision": CODE_REVISION,
        "expected_service_url_sha256": sha256_text(SERVICE_URL),
        "expected_man_id_sha256": man_id_sha256(MAN_ID),
        "expected_requests": 1000,
        "expected_concurrency": 4,
        "expected_max_rps": 2.0,
        "expected_service_timeout_seconds": 30.0,
        "expected_change_reference": CHANGE_REFERENCE,
        "validation_time": ACTIVE_TIME,
        "require_active_window": True,
    }
    arguments.update(overrides)
    return assess_online_load_plan(plan, **arguments)


class IstinaOnlineLoadPlanTests(unittest.TestCase):
    def test_exact_active_plan_passes(self):
        result = assess(valid_plan())

        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"], {"passed": 21, "failed": 0, "total": 21})

    def test_future_approved_plan_passes_preflight_but_not_execution(self):
        before_window = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)

        preflight = assess(
            valid_plan(),
            validation_time=before_window,
            require_active_window=False,
        )
        execution = assess(
            valid_plan(),
            validation_time=before_window,
            require_active_window=True,
        )

        self.assertTrue(preflight["verified"])
        self.assertFalse(execution["verified"])
        self.assertIn(
            "active_window",
            {failure["name"] for failure in execution["failures"]},
        )

    def test_expired_or_naive_window_fails_closed(self):
        expired = assess(
            valid_plan(),
            validation_time=datetime(2026, 7, 20, 12, 1, tzinfo=timezone.utc),
        )
        naive_plan = valid_plan()
        naive_plan["window"]["start"] = "2026-07-20T10:00:00"
        naive = assess(naive_plan)

        self.assertFalse(expired["verified"])
        self.assertFalse(naive["verified"])

    def test_every_execution_binding_is_exact(self):
        cases = {
            "dataset_sha256": {"expected_dataset_sha256": "c" * 64},
            "code_revision": {"expected_code_revision": "d" * 40},
            "service_url_sha256": {
                "expected_service_url_sha256": sha256_text(SERVICE_URL + "v2")
            },
            "man_id_sha256": {"expected_man_id_sha256": man_id_sha256(MAN_ID + 1)},
            "requests": {"expected_requests": 1001},
            "concurrency": {"expected_concurrency": 5},
            "max_rps": {"expected_max_rps": 2.1},
            "service_timeout_seconds": {
                "expected_service_timeout_seconds": 31.0
            },
            "change_reference": {"expected_change_reference": "OPS-OTHER"},
        }
        for expected_failure, overrides in cases.items():
            with self.subTest(expected_failure=expected_failure):
                result = assess(valid_plan(), **overrides)
                self.assertFalse(result["verified"])
                self.assertIn(
                    expected_failure,
                    {failure["name"] for failure in result["failures"]},
                )

    def test_unapproved_or_unqualified_approver_fails(self):
        for field, value in (("approved", False), ("approver_role", "student")):
            with self.subTest(field=field):
                plan = copy.deepcopy(valid_plan())
                plan["approval"][field] = value
                self.assertFalse(assess(plan)["verified"])

    def test_future_dated_approval_fails_even_for_preflight(self):
        plan = valid_plan()
        plan["approval"]["approved_at"] = "2026-07-20T09:45:00+00:00"

        result = assess(
            plan,
            validation_time=datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc),
            require_active_window=False,
        )

        self.assertFalse(result["verified"])
        self.assertIn(
            "approval_precedes_window",
            {failure["name"] for failure in result["failures"]},
        )


if __name__ == "__main__":
    unittest.main()
