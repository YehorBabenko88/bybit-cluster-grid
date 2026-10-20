import unittest
from audit.integration_ci.static_safety_scan import assess_text, scan_text

class StaticSafetyScanTests(unittest.TestCase):
    def test_forbidden_mutations(self):
        for command in ("Start-Service PostgreSQL", "Restart-Service grid",
                        "systemctl stop postgres", "initdb -D test",
                        "pg_ctl start", "psql -c 'select 1'",
                        "activate schema-2", "deploy schema_2",
                        "copy to LS5", "target LS-7"):
            with self.subTest(command=command):
                self.assertTrue(scan_text(command))
                self.assertEqual(assess_text(command)["status"], "BLOCKED_UNPROVEN")
    def test_clean_not_authorized(self):
        result = assess_text("python -m unittest discover")
        self.assertEqual(result["status"], "STATIC_SCAN_ONLY")
        self.assertFalse(result["execution_authorized"])
    def test_invalid_input(self):
        with self.assertRaises(TypeError):
            scan_text(None)

if __name__ == "__main__":
    unittest.main()
