import os
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/corporate_audit")

from fastapi.testclient import TestClient

from app import auth, main, processing


class ApiAuthzTests(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[auth.get_current_user] = lambda: "user-a"
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()

    def test_options_endpoint_denies_cross_user_access(self):
        with patch.object(main.db, "get_audit", return_value={"id": "audit-1", "user_id": "user-b"}):
            response = self.client.get("/api/audits/audit-1/options")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access denied", response.text)

    def test_status_endpoint_includes_quality_fields_for_needs_review(self):
        fake_audit = {
            "id": "audit-1",
            "user_id": "user-a",
            "status": "needs_review",
            "pipeline_state": "needs_review",
            "progress": "Manual review required before finalization.",
            "quality_report": {"review_required": True, "blocking_reasons": ["missing approvals"]},
            "review_required": True,
            "company_name": "Acme Corp",
            "documents": [],
            "timeline": [],
            "cap_table": [],
            "issues": [],
            "failed_documents": [],
        }
        with patch.object(main.db, "get_audit", return_value=fake_audit):
            response = self.client.get("/status/audit-1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "needs_review")
        self.assertEqual(body["pipeline_state"], "needs_review")
        self.assertTrue(body["review_required"])
        self.assertIn("quality_report", body)
        self.assertIsNotNone(body["results"])


class ApprovalAndQualityGateTests(unittest.TestCase):
    def test_batch_match_defaults_unmatched_to_warning(self):
        txs = [{
            "event_date": "2024-01-01",
            "event_type": "issuance",
            "shareholder_name": "Jane Doe",
            "share_delta": 1000,
            "source_doc_id": "doc-1",
        }]
        docs = [{
            "document_id": "approval-doc-1",
            "category": "Board/Shareholder Minutes",
            "filename": "minutes.pdf",
            "text": "Minutes excerpt",
        }]

        with patch("app.processing.extractor.call_claude", return_value="[]"):
            matched = processing.match_approvals_batch(txs, docs)

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["compliance_status"], "WARNING")
        self.assertIsNone(matched[0]["approval_doc_id"])
        self.assertIn("manual review", matched[0]["compliance_note"].lower())

    def test_no_approval_docs_marks_required_events_critical(self):
        txs = [
            {
                "event_date": "2024-01-01",
                "event_type": "issuance",
                "shareholder_name": "Jane Doe",
                "share_delta": 1000,
                "source_doc_id": "doc-1",
            },
            {
                "event_date": "2023-01-01",
                "event_type": "formation",
                "shareholder_name": None,
                "share_delta": 0,
                "source_doc_id": "doc-2",
            },
        ]

        matched = processing.match_approvals_batch(txs, [])
        self.assertEqual(matched[0]["compliance_status"], "CRITICAL")
        self.assertEqual(matched[1]["compliance_status"], "VERIFIED")

    def test_quality_report_requires_review_on_extraction_failure(self):
        docs = [{
            "filename": "stock_purchase.pdf",
            "parse_status": "success",
            "extracted_data": {
                "schema_version": "v1",
                "extraction": {
                    "stock_issuances": [{"error": "JSON parse failed"}]
                }
            }
        }]
        report = processing.build_quality_report(docs, transactions=[], issues=[])

        self.assertTrue(report["review_required"])
        self.assertGreater(report["extraction_failures"], 0)


if __name__ == "__main__":
    unittest.main()
