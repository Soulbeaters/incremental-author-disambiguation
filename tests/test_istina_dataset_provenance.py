import unittest

from evaluation.istina_dataset_provenance import assess_istina_provenance


def valid_manifest():
    return {
        "schema_version": 1,
        "source_system": "istina",
        "source_record_type": "publication_author_export",
        "identity_namespace": "istina_author_id",
        "label_semantics": "adjudicated_person_identity",
        "exported_at": "2026-07-01T00:00:00+00:00",
        "extraction_method": "approved read-only institutional export",
        "datasets": [{"name": "gold.json", "sha256": "abc"}],
        "independent_label_audit_verified": True,
        "cross_discipline_scope_verified": True,
        "approval": {
            "production_validation_approved": True,
            "approved_at": "2026-07-02T00:00:00+00:00",
            "reference": "approval-ticket-1",
        },
    }


class IstinaDatasetProvenanceTests(unittest.TestCase):
    def test_verified_manifest_requires_exact_dataset_hash(self):
        report = assess_istina_provenance(
            valid_manifest(),
            [{"name": "gold.json", "sha256": "abc"}],
        )

        self.assertTrue(report["verified"])

        mismatch = assess_istina_provenance(
            valid_manifest(),
            [{"name": "gold.json", "sha256": "different"}],
        )
        self.assertFalse(mismatch["verified"])
        self.assertIn(
            "dataset_hashes",
            {failure["name"] for failure in mismatch["failures"]},
        )

    def test_crossref_name_labels_cannot_claim_istina_identity_provenance(self):
        manifest = valid_manifest()
        manifest.update({
            "source_system": "crossref",
            "identity_namespace": "orcid",
            "label_semantics": "name_component_parse",
        })

        report = assess_istina_provenance(
            manifest,
            [{"name": "gold.json", "sha256": "abc"}],
        )

        self.assertFalse(report["verified"])
        failures = {failure["name"] for failure in report["failures"]}
        self.assertIn("source_system", failures)
        self.assertIn("identity_namespace", failures)
        self.assertIn("label_semantics", failures)


if __name__ == "__main__":
    unittest.main()
