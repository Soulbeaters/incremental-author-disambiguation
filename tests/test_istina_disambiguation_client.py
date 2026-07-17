# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.istina_disambiguation_client import (  # noqa: E402
    IstinaDisambiguationClient,
    IstinaServiceAuthor,
    istina_author_record_from_export,
    iter_istina_author_records,
    needs_short_family_middle_guard,
)
from integrations import IstinaDisambiguationClient as ExportedIstinaClient  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.content = json.dumps(payload).encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestIstinaDisambiguationClient(unittest.TestCase):
    def test_client_is_exported_from_integrations_package(self):
        self.assertIs(ExportedIstinaClient, IstinaDisambiguationClient)

    def test_istina_export_author_record_preserves_publication_context(self):
        article = {
            "id": 820111800,
            "title": "Arbitrary State Creation via Controlled Measurement",
            "doi": "10.2478/qic-2026-0006",
            "year": 2026,
            "authors": [
                {
                    "author_id": 466438876,
                    "original_name": "Zenchuk Alexander I.",
                    "position": 1,
                    "lastname": "Zenchuk",
                    "firstname": "Alexander",
                    "middlename": "I",
                },
                {
                    "author_id": 791078160,
                    "original_name": "Qi Wentao",
                    "position": 2,
                    "lastname": "Qi",
                    "firstname": "Wentao",
                    "middlename": "",
                },
            ],
        }

        record = istina_author_record_from_export(article, article["authors"][1])

        self.assertEqual(record.record_id, "istina:820111800:2")
        self.assertEqual(record.name, "Qi Wentao")
        self.assertEqual(record.coauthors, ["Zenchuk Alexander I."])
        self.assertEqual(record.publication_title, article["title"])
        self.assertEqual(record.year, 2026)
        self.assertEqual(record.source, "istina_export")

    def test_istina_export_author_record_builds_name_from_components(self):
        article = {"id": "a1", "authors": []}
        author = {"lastname": "Ma", "firstname": "Jiaxin", "middlename": ""}

        record = istina_author_record_from_export(article, author, fallback_position=1)

        self.assertEqual(record.record_id, "istina:a1:1")
        self.assertEqual(record.name, "Ma Jiaxin")

    def test_iter_istina_author_records_skips_empty_names(self):
        articles = [{
            "id": "a1",
            "authors": [
                {"original_name": "Wu Junde", "position": 1},
                {"lastname": "", "firstname": "", "position": 2},
            ],
        }]

        records = list(iter_istina_author_records(articles))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "Wu Junde")
        self.assertEqual(records[0].record_id, "istina:a1:1:1:1")

    def test_iter_istina_author_records_keeps_ids_unique_for_duplicate_article_ids(self):
        articles = [
            {"id": "same", "authors": [{"original_name": "Wu Junde", "position": 1}]},
            {"id": "same", "authors": [{"original_name": "Wu Junde", "position": 1}]},
        ]

        records = list(iter_istina_author_records(articles))

        self.assertEqual([record.record_id for record in records], [
            "istina:same:1:1:1",
            "istina:same:2:1:1",
        ])

    def test_iter_istina_author_records_keeps_ids_unique_for_duplicate_positions(self):
        articles = [{
            "id": "same",
            "authors": [
                {"original_name": "Wu Junde", "position": 1},
                {"original_name": "Wu Junde", "position": 1},
            ],
        }]

        records = list(iter_istina_author_records(articles))

        self.assertEqual([record.record_id for record in records], [
            "istina:same:1:1:1",
            "istina:same:1:1:2",
        ])

    def test_short_family_guard_detection(self):
        self.assertTrue(needs_short_family_middle_guard("Wu", "Junde", ""))
        self.assertTrue(needs_short_family_middle_guard("Ма", "Цзясин", ""))
        self.assertFalse(needs_short_family_middle_guard("Wang", "Yanhong", ""))
        self.assertFalse(needs_short_family_middle_guard("Ng", "Wee", "Han"))
        self.assertFalse(needs_short_family_middle_guard("Wu", "", ""))

    def test_from_exported_author_adds_query_only_dummy_middle_name(self):
        query = IstinaDisambiguationClient.from_exported_author({
            "lastname": "Wu",
            "firstname": "Junde",
            "middlename": "",
        })

        self.assertEqual(query.last_name, "Wu")
        self.assertEqual(query.first_name, "Junde")
        self.assertEqual(query.middle_name, "x")

    def test_from_exported_author_uses_cyrillic_dummy_middle_name(self):
        query = IstinaDisambiguationClient.from_exported_author({
            "lastname": "Ма",
            "firstname": "Цзясин",
            "middlename": "",
        })

        self.assertEqual(query.middle_name, "ч")

    def test_from_exported_author_splits_two_token_lastname_when_firstname_missing(self):
        query = IstinaDisambiguationClient.from_exported_author({
            "lastname": "Li Hui",
            "firstname": "",
            "middlename": "",
        })

        self.assertEqual(query.last_name, "Li")
        self.assertEqual(query.first_name, "Hui")
        self.assertEqual(query.middle_name, "x")

    def test_request_candidates_uses_expected_payload_shape(self):
        captured = {}

        def fake_post(url, headers, data, timeout):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = json.loads(data)
            captured["timeout"] = timeout
            return FakeResponse({
                "authors": [[{
                    "id": 637512347,
                    "last_name": "wu",
                    "first_name": "junde",
                    "middle_name": "",
                    "name_similarity": 0.85,
                }]],
                "authors_names": [{"last_name": "wu", "first_name": "junde", "middle_name": "x"}],
                "result_id": ["637512347"],
            })

        client = IstinaDisambiguationClient("http://example.invalid/", timeout=3, post_func=fake_post)
        response = client.request_candidates([IstinaServiceAuthor("Wu", "Junde", "x")], man_id=4705445)

        self.assertEqual(captured["url"], "http://example.invalid/")
        self.assertEqual(captured["headers"], {"Content-Type": "application/json"})
        self.assertEqual(captured["timeout"], 3)
        self.assertEqual(captured["data"], {
            "authors": [{"last_name": "Wu", "first_name": "Junde", "middle_name": "x"}],
            "man_id": 4705445,
        })
        self.assertEqual(response["result_id"], ["637512347"])

    def test_conservative_decision_accepts_unique_exact_candidate_with_service_agreement(self):
        response = {
            "authors": [[
                {
                    "id": 637512347,
                    "last_name": "wu",
                    "first_name": "junde",
                    "middle_name": "",
                    "name_similarity": 0.85,
                },
                {
                    "id": 387863,
                    "last_name": "wu",
                    "first_name": "j",
                    "middle_name": "",
                    "name_similarity": 0.765,
                },
            ]],
            "result_id": ["637512347"],
        }

        decision = IstinaDisambiguationClient.conservative_local_decision(
            IstinaServiceAuthor("Wu", "Junde", "x"),
            response,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "service_agrees_with_unique_exact_candidate")
        self.assertEqual(decision.candidate.id, "637512347")

    def test_conservative_decision_rejects_service_disagreement(self):
        response = {
            "authors": [[{
                "id": 637512347,
                "last_name": "wu",
                "first_name": "junde",
                "middle_name": "",
                "name_similarity": 0.85,
            }]],
            "result_id": ["0"],
        }

        decision = IstinaDisambiguationClient.conservative_local_decision(
            IstinaServiceAuthor("Wu", "Junde", "x"),
            response,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "service_result_disagrees")

    def test_conservative_decision_rejects_initial_firstname(self):
        response = {
            "authors": [[{
                "id": 3457446,
                "last_name": "he",
                "first_name": "j",
                "middle_name": "",
                "name_similarity": 0.85,
            }]],
            "result_id": ["3457446"],
        }

        decision = IstinaDisambiguationClient.conservative_local_decision(
            IstinaServiceAuthor("HE", "J", "x"),
            response,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "ambiguous_initial_firstname")

    def test_conservative_decision_rejects_multiple_exact_candidates(self):
        response = {
            "authors": [[
                {
                    "id": 1,
                    "last_name": "xu",
                    "first_name": "bo",
                    "middle_name": "",
                    "name_similarity": 0.85,
                },
                {
                    "id": 2,
                    "last_name": "xu",
                    "first_name": "bo",
                    "middle_name": "",
                    "name_similarity": 0.86,
                },
            ]],
            "result_id": ["1"],
        }

        decision = IstinaDisambiguationClient.conservative_local_decision(
            IstinaServiceAuthor("Xu", "Bo", "x"),
            response,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "not_unique_exact_candidate")

    def test_known_author_unknown_fallback_accepts_known_high_similarity_result(self):
        response = {
            "authors": [[{
                "id": 1758243,
                "last_name": "roberts",
                "first_name": "c",
                "middle_name": "",
                "name_similarity": 0.85,
            }]],
            "result_id": ["1758243"],
        }

        decision = IstinaDisambiguationClient.known_author_unknown_fallback(
            response,
            known_author_ids={"1758243"},
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "known_author_service_fallback")
        self.assertEqual(decision.candidate.id, "1758243")

    def test_known_author_unknown_fallback_rejects_unseen_result(self):
        response = {
            "authors": [[{
                "id": 233942680,
                "last_name": "volchugov",
                "first_name": "p",
                "middle_name": "",
                "name_similarity": 0.85,
            }]],
            "result_id": ["233942680"],
        }

        decision = IstinaDisambiguationClient.known_author_unknown_fallback(
            response,
            known_author_ids={"1758243"},
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "service_result_not_in_local_history")

    def test_known_author_unknown_fallback_rejects_low_similarity(self):
        response = {
            "authors": [[{
                "id": 1078148,
                "last_name": "mu",
                "first_name": "l",
                "middle_name": "",
                "name_similarity": 0.602083,
            }]],
            "result_id": ["1078148"],
        }

        decision = IstinaDisambiguationClient.known_author_unknown_fallback(
            response,
            known_author_ids={"1078148"},
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "service_name_similarity_below_threshold")

    def test_known_author_unknown_fallback_rejects_nonfinite_similarity(self):
        response = {
            "authors": [[{
                "id": 1078148,
                "last_name": "mu",
                "first_name": "l",
                "middle_name": "",
                "name_similarity": float("nan"),
            }]],
            "result_id": ["1078148"],
        }

        decision = IstinaDisambiguationClient.known_author_unknown_fallback(
            response,
            known_author_ids={"1078148"},
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "service_name_similarity_below_threshold")


if __name__ == "__main__":
    unittest.main()
