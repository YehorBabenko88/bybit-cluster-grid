import unittest
from audit.integration_ci.pg_pytest_receipt import validate_receipt

SHA = "a" * 40


def xml(count=23, bad=None):
    cases = []
    for index in range(count):
        extra = "<skipped/>" if bad == "skip" and index == 0 else (
            "<failure/>" if bad == "fail" and index == 0 else "")
        cases.append(f'<testcase classname="tests.test_pgdata_cross_contract" name="test_{index}">{extra}</testcase>')
    return "<testsuite>" + "".join(cases) + "</testsuite>"


class PgPytestReceiptTests(unittest.TestCase):
    def test_expected_receipt_is_metadata_only(self):
        self.assertEqual(validate_receipt(xml(), SHA, SHA), [])

    def test_missing_coverage_fails(self):
        for count in (0, 1, 22):
            self.assertIn("PG_CROSS_CONTRACT_CASES_MISSING", validate_receipt(xml(count), SHA, SHA))

    def test_skips_and_failures_are_forbidden(self):
        for bad in ("skip", "fail"):
            self.assertIn("SKIPPED_OR_FAILED_CASE", validate_receipt(xml(bad=bad), SHA, SHA))

    def test_wrong_commit_or_scope_is_forbidden(self):
        self.assertIn("HEAD_SHA_MISMATCH", validate_receipt(xml(), "b"*40, SHA))
        self.assertIn("UNEXPECTED_TEST_SCOPE", validate_receipt(xml().replace(
            "tests.test_pgdata_cross_contract", "tests.unrelated", 1), SHA, SHA))

    def test_invalid_xml_is_forbidden(self):
        self.assertIn("INVALID_JUNIT_XML", validate_receipt("<bad", SHA, SHA))


    def test_duplicate_cases_cannot_inflate_count(self):
        single = '<testcase classname="tests.test_pgdata_cross_contract" name="same"/>'
        report = "<testsuite>" + single * 23 + "</testsuite>"
        self.assertIn("DUPLICATE_TESTCASE", validate_receipt(report, SHA, SHA))

    def test_missing_case_identity_rejected(self):
        report = xml().replace(' name="test_0"', '', 1)
        self.assertIn("MALFORMED_TESTCASE", validate_receipt(report, SHA, SHA))
