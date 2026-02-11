import os
import unittest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app import processing


class CapTableMatchingTests(unittest.TestCase):
    def test_does_not_last_name_match_different_people(self):
        carta = [{"name": "Jane Smith", "shares": 1000}]
        generated = [{"shareholder": "John Smith", "shares": 1000}]

        issues = processing.compare_cap_tables(carta, generated)
        descriptions = [issue.get("description", "") for issue in issues]

        self.assertTrue(any("was not found in source documents" in d for d in descriptions))
        self.assertFalse(any("Share count mismatch" in d for d in descriptions))

    def test_duplicate_entries_are_aggregated_and_flagged(self):
        carta = [
            {"name": "Alex Roe", "shares": 400},
            {"name": "Alex Roe", "shares": 600},
        ]
        generated = [{"shareholder": "Alex Roe", "shares": 1000}]

        issues = processing.compare_cap_tables(carta, generated)
        descriptions = [issue.get("description", "") for issue in issues]

        self.assertTrue(any("duplicate shareholder entries" in d.lower() for d in descriptions))
        self.assertFalse(any("Share count mismatch" in d for d in descriptions))


class QualityGateTests(unittest.TestCase):
    def test_quality_report_requires_review_on_parse_failure(self):
        docs = [{
            "filename": "broken.pdf",
            "parse_status": "error",
            "extracted_data": {
                "schema_version": "v1",
                "extraction": {}
            }
        }]
        report = processing.build_quality_report(docs, transactions=[], issues=[])

        self.assertTrue(report["review_required"])
        self.assertGreaterEqual(len(report["blocking_reasons"]), 1)


if __name__ == "__main__":
    unittest.main()
