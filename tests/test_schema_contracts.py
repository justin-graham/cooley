import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class SchemaContractTests(unittest.TestCase):
    def test_migration_001_defines_required_document_and_event_columns(self):
        sql = (REPO_ROOT / "migrations" / "001_add_equity_tables.sql").read_text(encoding="utf-8")
        normalized = " ".join(sql.lower().split())

        self.assertIn("parse_status", normalized)
        self.assertIn("parse_error", normalized)
        self.assertIn("preview_image", normalized)
        self.assertIn("summary", normalized)

    def test_schema_sql_contains_quality_gate_columns(self):
        sql = (REPO_ROOT / "schema.sql").read_text(encoding="utf-8")
        normalized = " ".join(sql.lower().split())

        self.assertIn("pipeline_state", normalized)
        self.assertIn("quality_report", normalized)
        self.assertIn("review_required", normalized)
        self.assertIn("create table if not exists sessions", normalized)

        # Ensure explicit needs_review state is accepted in audits status checks.
        self.assertIn("needs_review", normalized)

    def test_migration_quickstart_includes_hardening_migration(self):
        guide = (REPO_ROOT / "MIGRATION_QUICKSTART.md").read_text(encoding="utf-8")
        self.assertIn("003_production_hardening.sql", guide)


if __name__ == "__main__":
    unittest.main()
