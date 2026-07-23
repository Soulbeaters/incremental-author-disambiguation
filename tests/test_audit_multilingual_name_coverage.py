from experiments.audit_multilingual_name_coverage import audit


def test_audit_reports_only_aggregate_multilingual_opportunities():
    rows = [
        {
            "firstname": "Цзясин",
            "middlename": "",
            "lastname": "Ма",
            "orcid": "private-id",
            "original_name": "must-not-be-read",
        },
        {
            "firstname": "Jiaxing",
            "middlename": "",
            "lastname": "Ma",
            "orcid": "private-id",
            "original_name": "must-not-be-read",
        },
        {
            "firstname": "Unlabelled",
            "middlename": "",
            "lastname": "Person",
            "orcid": "",
            "original_name": "must-not-be-read",
        },
    ]

    result = audit(rows)

    assert result["rows"] == 3
    assert result["usable_structured_rows"] == 3
    assert result["mixed_script_identities"]["total"] == 1
    assert (
        result["same_identity_pair_opportunities"][
            "palladius_rescue_at_0_95"
        ]
        == 1
    )
    assert result["unstructured_name_fields_read"] is False
    assert "private-id" not in str(result)
    assert "must-not-be-read" not in str(result)
