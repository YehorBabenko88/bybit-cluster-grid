import unittest
from audit.integration_ci.pg_pytest_receipt import validate_receipt

SHA = "a" * 40
NAMES = ("test_normal_metadata_still_blocked", "test_missing_or_forged_inputs_fail_closed",
         "test_no_side_effects", "test_specific_blocker_codes_and_immutable_inputs",
         "test_behavioral_journal_objects_never_compared", "test_all_journal_scalar_fields_reject_non_strings",
         "test_adapter_identity_mismatch_codes", "test_schema2_is_never_accepted",
         "test_hostile_journal_cannot_mutate_plan_through_comparison",
         "test_string_subclasses_not_accepted_as_journal_claims",
         "test_protected_nodes_and_unsafe_path_aliases_remain_blocked",
         "test_missing_adapter_root_cannot_suppress_layout_blocker",
         "test_metadata_matching_cannot_claim_ownership_or_authorize",
         "test_all_missing_journal_fields_fail_closed",
         "test_missing_adapter_identity_fields_fail_closed",
         "test_behavioral_adapter_fields_never_compared",
         "test_repeated_calls_are_deterministic_and_do_not_accumulate_blockers",
         "test_result_mutation_cannot_affect_future_checks",
         "test_plan_malformed_shape_never_calls_adapter_or_journal_objects",
         "test_invalid_plan_fields_are_rejected_without_execution",
         "test_non_dictionary_journal_and_adapter_are_rejected",
         "test_journal_boolean_authorization_flags_use_exact_false",
         "test_journal_mismatches_report_specific_blockers",
         "test_real_powershell_jsonl_is_distinguished_from_diagnostic_envelope",
         "test_producer_journal_mutations_fail_closed",
         "test_extra_diagnostic_envelope_claims_are_not_trusted",
         "test_real_adapter_pgdata_layout_remains_incompatible")
COLLECTED = ["tests/test_pgdata_cross_contract.py::" + n for n in NAMES]


def xml(names=NAMES, classname="tests.test_pgdata_cross_contract", bad=None, declared=None):
    cases = []
    for index, name in enumerate(names):
        extra = ("<" + bad + "/>") if bad and index == 0 else ""
        cases.append(f'<testcase classname="{classname}" name="{name}">{extra}</testcase>')
    attrib = f' tests="{declared}"' if declared is not None else ""
    return "<testsuite" + attrib + ">" + "".join(cases) + "</testsuite>"


class PgPytestReceiptTests(unittest.TestCase):
    def test_exact_collection_metadata_only(self):
        self.assertEqual(validate_receipt(xml(), SHA, SHA, COLLECTED), [])

    def test_requires_collection(self):
        self.assertIn("COLLECTION_REQUIRED", validate_receipt(xml(), SHA, SHA))
        self.assertIn("COLLECTION_REQUIRED", validate_receipt(xml(), SHA, SHA, []))
        self.assertIn("COLLECTION_REQUIRED", validate_receipt(xml(), SHA, SHA, COLLECTED + COLLECTED[:1]))

    def test_forged_names_rejected(self):
        fake = ["invented_" + str(i) for i in range(23)]
        self.assertIn("COLLECTION_JUNIT_MISMATCH", validate_receipt(xml(fake), SHA, SHA, COLLECTED))

    def test_partial_23_of_27_rejected(self):
        self.assertIn("COLLECTION_JUNIT_MISMATCH", validate_receipt(xml(NAMES[:23]), SHA, SHA, COLLECTED))

    def test_substring_classname_rejected(self):
        self.assertIn("UNEXPECTED_TEST_SCOPE", validate_receipt(
            xml(classname="evil.test_pgdata_cross_contract_not_real"), SHA, SHA, COLLECTED))

    def test_unexpected_class_or_path_rejected(self):
        self.assertIn("UNEXPECTED_TEST_SCOPE", validate_receipt(
            xml(classname="test_pgdata_cross_contract"), SHA, SHA, COLLECTED))
        self.assertIn("UNEXPECTED_TEST_SCOPE", validate_receipt(
            xml().replace('name="test_normal_metadata_still_blocked"',
                          'file="tests/fake.py" name="test_normal_metadata_still_blocked"'),
            SHA, SHA, COLLECTED))

    def test_skips_failures_errors_are_forbidden(self):
        for tag in ("skipped", "failure", "error"):
            self.assertIn("SKIPPED_OR_FAILED_CASE", validate_receipt(xml(bad=tag), SHA, SHA, COLLECTED))

    def test_duplicate_and_malformed_cases(self):
        self.assertIn("DUPLICATE_TESTCASE", validate_receipt(xml(NAMES + NAMES[:1]), SHA, SHA, COLLECTED))
        self.assertIn("UNEXPECTED_TEST_SCOPE", validate_receipt(
            xml().replace('name="test_normal_metadata_still_blocked"', 'name=""'), SHA, SHA, COLLECTED))

    def test_wrong_sha(self):
        self.assertIn("HEAD_SHA_MISMATCH", validate_receipt(xml(), "b" * 40, SHA, COLLECTED))

    def test_bad_xml_and_root(self):
        self.assertIn("INVALID_JUNIT_XML", validate_receipt("<bad", SHA, SHA, COLLECTED))
        self.assertIn("INVALID_JUNIT_ROOT", validate_receipt(
            xml().replace("testsuite", "untrusted"), SHA, SHA, COLLECTED))

    def test_declared_counts_and_empty_receipt(self):
        self.assertIn("JUNIT_SUITE_COUNTS_MISMATCH", validate_receipt(xml(declared=999), SHA, SHA, COLLECTED))
        self.assertIn("ZERO_TESTS", validate_receipt("<testsuite/>", SHA, SHA, COLLECTED))

    def test_unbounded_junit_cases_rejected(self):
        repeated = NAMES * 371
        self.assertIn("JUNIT_CASE_LIMIT_EXCEEDED", validate_receipt(xml(repeated), SHA, SHA, COLLECTED))

    def test_tampered_collected_inventory_rejected(self):
        self.assertIn("COLLECTION_REQUIRED", validate_receipt(xml(), SHA, SHA, ["wrong::test_case"]))
        self.assertIn("COLLECTION_REQUIRED", validate_receipt(xml(), SHA, SHA, None))

    def test_invalid_collected_json_must_not_hide_valid_junit(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from audit.integration_ci import pg_pytest_receipt
        with TemporaryDirectory() as directory:
            junit = Path(directory) / "results.xml"
            collected = Path(directory) / "collected.json"
            junit.write_text(xml(), encoding="utf-8")
            collected.write_text("27 tests collected in 0.07s\\n" + "[]", encoding="utf-8")
            with patch("sys.argv", ["receipt", "--junit", str(junit), "--collected", str(collected),
                                    "--sha", SHA, "--expected-sha", SHA]):
                self.assertEqual(pg_pytest_receipt.main(), 1)
            self.assertEqual(validate_receipt(junit.read_text(encoding="utf-8"), SHA, SHA, None),
                             ["COLLECTION_REQUIRED"])

    def test_suite_level_failure_or_skip_cannot_be_hidden(self):
        for tag in ("failure", "error", "skipped"):
            report = xml().replace("</testsuite>", f"<{tag}/></testsuite>")
            self.assertIn("SKIPPED_OR_FAILED_CASE", validate_receipt(report, SHA, SHA, COLLECTED))
