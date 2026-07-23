import json

from experiments.audit_ruzh_istina_coverage import audit


def test_audit_is_aggregate_only_and_ignores_original_name(tmp_path):
    dataset = tmp_path / "istina.json"
    dataset.write_text(json.dumps([
        {
            "id": "paper-1",
            "year": 2022,
            "authors": [
                {
                    "author_id": "A",
                    "firstname": "Jiaxing",
                    "lastname": "Ma",
                    "position": 1,
                    "original_name": "fabricated-one",
                },
                {
                    "author_id": "A",
                    "firstname": "Jiaxing",
                    "lastname": "Ma",
                    "position": 1,
                    "original_name": "fabricated-two",
                },
            ],
        },
        {
            "id": "paper-2",
            "year": 2024,
            "authors": [{
                "author_id": "A",
                "firstname": "Цзясин",
                "lastname": "Ма",
                "position": 1,
                "original_name": "also-fabricated",
            }],
        },
    ], ensure_ascii=False), encoding="utf-8")

    result = audit(dataset, cutoff_year=2023)

    assert result["original_name_read"] is False
    assert result["input"]["exact_whitelisted_duplicates_removed"] == 1
    assert result["coverage"]["target_authorships"] == 2
    assert result["temporal"] == {
        "history_through_year": 2023,
        "target_test": 1,
        "target_known": 1,
        "target_new": 0,
    }
    assert "records" not in result
