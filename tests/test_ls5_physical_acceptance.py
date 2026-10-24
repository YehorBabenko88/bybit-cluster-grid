import hashlib
import json
import unittest

from installer.ls5_physical_acceptance import (
    AcceptanceBlocked, CASES, STAGES, decide, validate_metadata, verify_artifacts,
)

HEAD = "e25197b169ef0e5f37b5bd0030ee4a97b13965e2"


def receipt(stage="pc4_sid_acl"):
    return {"schema": 1, "head": HEAD, "stage": stage, "source": "offline",
            "status": "BLOCKED", "assurance": "SYNTHETIC_PASS",
            "cases": ([{"name": n, "status": "NOT_RUN", "assurance": "BLOCKED_UNPROVEN"}
                       for n in CASES] if stage == "pc4_sid_acl" else []), "metadata": {}}


def bundle(names=("one", "two")):
    junit = ('<testsuite head="' + HEAD + '" tests="' + str(len(names)) +
             '" failures="0" errors="0" skipped="0">' +
             ''.join('<testcase name="' + n + '"/>' for n in names) +
             '</testsuite>').encode()
    jsonl = b"".join((json.dumps({"head": HEAD, "name": n, "status": "PASS",
                                  "assurance": "SYNTHETIC_PASS"}) + "\n").encode()
                     for n in names)
    index = json.dumps({"head": HEAD, "files": {
        "results.xml": hashlib.sha256(junit).hexdigest(),
        "events.jsonl": hashlib.sha256(jsonl).hexdigest()}}).encode()
    return dict(head=HEAD, inventory=list(names), junit=junit, jsonl=jsonl, index=index)


class GateTests(unittest.TestCase):
    def test_pc4_ten_not_run_never_physical(self):
        result = validate_metadata(json.dumps(receipt()).encode(), expected_head=HEAD)
        self.assertEqual(result["pc4_cases_not_run"], 10)
        self.assertFalse(result["physical_pass"])

    def test_all_stages_remain_blocked(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(validate_metadata(json.dumps(receipt(stage)).encode(),
                                                   expected_head=HEAD)["status"], "BLOCKED")

    def test_wrong_head_denied(self):
        with self.assertRaises(AcceptanceBlocked):
            validate_metadata(json.dumps(receipt()).encode(), expected_head="f" * 40)

    def test_schema2_nested_and_forged_authority_denied(self):
        for field in ("schema2", "schema2_enabled", "schema_2_enabled",
                      "execution_authorized", "deployment_authorized"):
            for value in (True, 1, 0, None, "false"):
                x = receipt()
                x["metadata"] = {"opaque": [{"claim": {field: value}}]}
                with self.subTest(field=field, value=value), self.assertRaises(AcceptanceBlocked):
                    validate_metadata(json.dumps(x).encode(), expected_head=HEAD)

    def test_case_promotions_denied(self):
        for mutation in ("missing", "reordered", "pass", "duplicate"):
            x = receipt()
            if mutation == "missing":
                x["cases"].pop()
            elif mutation == "reordered":
                x["cases"].reverse()
            elif mutation == "pass":
                x["cases"][0]["status"] = "PASS"
            else:
                x["cases"][1] = dict(x["cases"][0])
            with self.subTest(mutation=mutation), self.assertRaises(AcceptanceBlocked):
                validate_metadata(json.dumps(x).encode(), expected_head=HEAD)

    def test_duplicate_json_key_denied(self):
        raw = json.dumps(receipt()).replace('"schema": 1', '"schema": 1, "schema": 1')
        with self.assertRaises(AcceptanceBlocked):
            validate_metadata(raw.encode(), expected_head=HEAD)

    def test_valid_offline_bundle_never_physical(self):
        result = verify_artifacts(**bundle())
        self.assertEqual(result["status"], "SYNTHETIC_PASS")
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["deployment_go"])

    def test_artifact_adversaries(self):
        original = bundle()
        mutations = []
        x = dict(original); x["head"] = "f" * 40; mutations.append(x)
        x = dict(original); x["inventory"] = ["one", "one"]; mutations.append(x)
        x = dict(original); x["inventory"] = ["two", "one"]; mutations.append(x)
        x = dict(original); x["junit"] = x["junit"].replace(b'failures="0"', b'failures="1"'); mutations.append(x)
        x = dict(original); x["jsonl"] = x["jsonl"] + b'{"head":"wrong"}\n'; mutations.append(x)
        x = dict(original); x["index"] = x["index"].replace(b'"files":', b'"files": {}, "files":'); mutations.append(x)
        x = dict(original); x["junit"] = b'<!DOCTYPE testsuite>' + x["junit"]; mutations.append(x)
        x = dict(original); x["jsonl"] = x["jsonl"].replace(b'"SYNTHETIC_PASS"', b'"PHYSICAL_PASS"'); mutations.append(x)
        for i, x in enumerate(mutations):
            with self.subTest(i=i), self.assertRaises(AcceptanceBlocked):
                verify_artifacts(**x)

    def test_claimed_all_pass_does_not_authorize(self):
        x = decide({s: "PHYSICAL_PASS" for s in STAGES})
        self.assertEqual(x["status"], "BLOCKED")
        self.assertFalse(x["deployment_go"])

    def test_fail_is_fail(self):
        x = {s: "BLOCKED" for s in STAGES}
        x["acl_remediation"] = "FAIL"
        self.assertEqual(decide(x)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
