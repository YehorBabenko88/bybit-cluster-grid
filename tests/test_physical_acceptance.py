import hashlib
import json
import unittest

from installer.physical_acceptance import (
    AcceptanceBlocked, DOMAINS, PHYSICAL_CASES, assess, validate_receipt, verify_jsonl, verify_junit, verify_sha256_index,
)


def receipt(stage="pc4_sid_acl"):
    names = PHYSICAL_CASES if stage == "pc4_sid_acl" else (
        tuple(f"vm_case_{i:02}" for i in range(1, 13)) if stage == "vm_lab" else ())
    return {
        "schema": 1, "run_id": "pc4-lab-0001", "host": "PC4",
        "source_sha": "a" * 40, "package_sha256": "b" * 64,
        "stage": stage, "mode": "PLAN_ONLY", "status": "BLOCKED",
        "cases": [{"name": name, "status": "NOT_RUN", "assurance": "BLOCKED_UNPROVEN"}
                  for name in names],
        "metadata": {},
    }


class AcceptanceTests(unittest.TestCase):
    def test_plan_only_ten_cases_stays_blocked(self):
        result = validate_receipt(receipt())
        self.assertEqual(result["cases_not_run"], 10)
        self.assertEqual(result["verified_cases"], 0)
        self.assertFalse(result["execution_authorized"])

    def test_vm_twelve_cases_stay_blocked(self):
        self.assertEqual(validate_receipt(receipt("vm_lab"))["cases_not_run"], 12)

    def test_other_stages_cannot_invent_cases(self):
        for stage in DOMAINS:
            if stage in ("pc4_sid_acl", "vm_lab"):
                continue
            with self.subTest(stage=stage):
                self.assertEqual(validate_receipt(receipt(stage))["status"], "BLOCKED")

    def test_all_positive_or_malformed_cases_denied(self):
        for name, field, value in (
            ("pass", "status", "PASS"), ("skipped", "status", "SKIPPED"),
            ("fail", "status", "FAIL"), ("assurance", "assurance", "PASS"),
        ):
            with self.subTest(name=name):
                item = receipt()
                item["cases"][0][field] = value
                with self.assertRaises(AcceptanceBlocked):
                    validate_receipt(item)

    def test_case_identity_and_count_denied(self):
        for change in ("missing", "duplicate", "wrong_order"):
            item = receipt()
            if change == "missing":
                item["cases"].pop()
            elif change == "duplicate":
                item["cases"][1] = dict(item["cases"][0])
            else:
                item["cases"].reverse()
            with self.subTest(change=change), self.assertRaises(AcceptanceBlocked):
                validate_receipt(item)

    def test_schema2_nested_aliases_denied(self):
        for alias in ("schema2", "schema2_enabled", "schema_2_enabled"):
            for value in (True, 1, 0, None, "false"):
                item = receipt()
                item["metadata"] = {"opaque": [{"payload": {alias: value}}]}
                with self.subTest(alias=alias, value=value), self.assertRaises(AcceptanceBlocked):
                    validate_receipt(item)

    def test_synthetic_sources_never_pass(self):
        item = receipt()
        item["metadata"] = {"sources": ["witnessA", "witnessB"], "synthetic_result": "PASS"}
        self.assertEqual(validate_receipt(item)["status"], "BLOCKED")

    def test_real_execute_not_accepted(self):
        item = receipt()
        item["mode"] = "EXECUTE"
        with self.assertRaises(AcceptanceBlocked):
            validate_receipt(item)

    def test_aggregate_never_authorizes_even_if_all_claim_pass(self):
        result = assess({d: "PASS" for d in DOMAINS}, approvals_verified=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["deployment_authorized"])

    def test_aggregate_failure_is_fail(self):
        matrix = {d: "BLOCKED" for d in DOMAINS}
        matrix["network"] = "FAIL"
        self.assertEqual(assess(matrix)["status"], "FAIL")

    def test_jsonl_digest_and_identity(self):
        raw = b'{"run_id":"pc4-lab-0001","event":"plan"}\n'
        self.assertEqual(verify_jsonl(raw, expected_run_id="pc4-lab-0001",
                                     expected_sha256=hashlib.sha256(raw).hexdigest()), 1)
        for malformed in (
            b'{"run_id":"pc4-lab-0001","run_id":"pc4-lab-0001"}\n',
            b'{"run_id":"other"}\n',
            b'{"run_id":"pc4-lab-0001","schema2_enabled":true}\n',
            b'{"run_id":"pc4-lab-0001"}\r\n',
            b'[1,2,3]\n',
            b'{"run_id":"pc4-lab-0001","x":NaN}\n',
        ):
            with self.subTest(malformed=malformed), self.assertRaises(AcceptanceBlocked):
                verify_jsonl(malformed, expected_run_id="pc4-lab-0001",
                             expected_sha256=hashlib.sha256(malformed).hexdigest())


    def test_junit_only_not_run_is_accepted_as_blocked(self):
        cases = ("collector_token", "storage_token")
        raw = (b'<testsuite run_id="pc4-lab-0001" tests="2" failures="0" errors="0" skipped="2">'
               b'<testcase name="collector_token"><skipped/></testcase>'
               b'<testcase name="storage_token"><skipped/></testcase></testsuite>')
        self.assertEqual(verify_junit(raw, expected_cases=cases,
                                      expected_run_id="pc4-lab-0001")["status"], "BLOCKED")
        forged = (
            raw.replace(b'skipped="2"', b'skipped="0"'),
            raw.replace(b'<skipped/>', b'', 1),
            raw.replace(b'collector_token', b'storage_token'),
            raw.replace(b'run_id="pc4-lab-0001"', b'run_id="other"'),
            raw.replace(b'<skipped/>', b'<failure/>', 1),
            b'<!DOCTYPE testsuite [<!ENTITY x "oops">]>' + raw,
        )
        for item in forged:
            with self.subTest(item=item[:80]), self.assertRaises(AcceptanceBlocked):
                verify_junit(item, expected_cases=cases, expected_run_id="pc4-lab-0001")

    def test_sha256_index_exact_inventory_and_bytes(self):
        files = {"events.jsonl": b'{"run_id":"pc4-lab-0001"}\\n',
                 "results.xml": b"<testsuite/>"}
        index = json.dumps({"schema": 1, "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        }}).encode()
        result = verify_sha256_index(index, files)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["provenance_verified"])
        for bad_index, bad_files in (
            (index, {"events.jsonl": b"changed", "results.xml": files["results.xml"]}),
            (index, {"events.jsonl": files["events.jsonl"]}),
            (index.replace(b'"schema": 1', b'"schema": 2'), files),
            (index.replace(b'"files":', b'"files": {}, "files":'), files),
        ):
            with self.subTest(index=bad_index[:50]), self.assertRaises(AcceptanceBlocked):
                verify_sha256_index(bad_index, bad_files)


if __name__ == "__main__":
    unittest.main()
