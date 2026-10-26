import hashlib
import json
import unittest

from installer.ls5_physical_acceptance import (
    AcceptanceBlocked, CASES, STAGES, REQUIRED_WORKFLOWS, audit_workflow_runs, audit_evidence_chain, audit_gate_dependencies, audit_ci_matrix, audit_cross_pr_gates, decide, validate_metadata, verify_artifacts,
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
        x = dict(original); x["inventory"] = [1, 1]; mutations.append(x)
        x = dict(original); x["inventory"] = [{"name": "one"}]; mutations.append(x)
        x = dict(original); x["inventory"] = ["two", "one"]; mutations.append(x)
        x = dict(original); x["junit"] = x["junit"].replace(b'failures="0"', b'failures="1"'); mutations.append(x)
        x = dict(original); x["jsonl"] = x["jsonl"] + b'{"head":"wrong"}\n'; mutations.append(x)
        x = dict(original); x["index"] = x["index"].replace(b'"files":', b'"files": {}, "files":'); mutations.append(x)
        x = dict(original); x["junit"] = b'<!DOCTYPE testsuite>' + x["junit"]; mutations.append(x)
        x = dict(original); x["junit"] = x["junit"].replace(b'<testcase name="one"/>', b'<testcase name="one" extra="forged"/>'); mutations.append(x)
        x = dict(original); x["junit"] = x["junit"].replace(b'tests="2"', b'tests="2" extra="forged"'); mutations.append(x)
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

    def test_required_workflows_and_skips_never_physical(self):
        runs = [
            {"name": name, "head": HEAD, "run_id": i + 1, "attempt": 1,
             "status": "completed", "conclusion": "success"}
            for i, name in enumerate(sorted(REQUIRED_WORKFLOWS))
        ]
        result = audit_workflow_runs(runs, expected_head=HEAD)
        self.assertTrue(result["offline_ci_complete"])
        self.assertFalse(result["artifacts_independently_verified"])
        self.assertFalse(result["deployment_go"])
        for status, conclusion in (("completed", "skipped"), ("queued", None),
                                   ("completed", "failure")):
            modified = [dict(x) for x in runs]
            modified[0].update(status=status, conclusion=conclusion)
            with self.subTest(status=status, conclusion=conclusion):
                result = audit_workflow_runs(modified, expected_head=HEAD)
                self.assertFalse(result["offline_ci_complete"])
        self.assertFalse(audit_workflow_runs(runs[:-1], expected_head=HEAD)["offline_ci_complete"])

    def test_workflow_wrong_head_and_duplicate_denied(self):
        item = {"name": "preflight", "head": HEAD, "run_id": 42, "attempt": 1,
                "status": "completed", "conclusion": "success"}
        for bad in ([item, item], [dict(item, head="f" * 40)],
                    [dict(item, run_id=True)], [dict(item, status="queued")]):
            with self.subTest(bad=bad), self.assertRaises(AcceptanceBlocked):
                audit_workflow_runs(bad, expected_head=HEAD)


    def test_cross_artifact_identity_and_attempt(self):
        x = {"head": HEAD, "run_id": 1234, "attempt": 2, "artifact_id": 987,
             "zip_sha256": "a" * 64, "manifest_head": HEAD,
             "junit_head": HEAD, "jsonl_head": HEAD,
             "manifest_run_id": 1234, "junit_run_id": 1234,
             "jsonl_run_id": 1234, "manifest_attempt": 2,
             "junit_attempt": 2, "jsonl_attempt": 2,
             "custody": "UNVERIFIED", "source": "GITHUB_HOSTED_SYNTHETIC"}
        result = audit_evidence_chain(x, expected_head=HEAD)
        self.assertTrue(result["internal_identity_consistent"])
        self.assertFalse(result["custody_authenticated"])
        self.assertFalse(result["deployment_go"])
        for field, value in (
            ("head", "f" * 40), ("manifest_head", "f" * 40),
            ("junit_head", "f" * 40), ("jsonl_head", "f" * 40),
            ("manifest_run_id", 1235), ("junit_run_id", 1235),
            ("jsonl_run_id", 1235), ("manifest_attempt", 1),
            ("junit_attempt", 1), ("jsonl_attempt", 1),
            ("run_id", True), ("attempt", 0), ("artifact_id", 0),
            ("zip_sha256", "0"), ("custody", "VERIFIED"),
            ("source", "PHYSICAL_HOST"),
        ):
            with self.subTest(field=field), self.assertRaises(AcceptanceBlocked):
                audit_evidence_chain(dict(x, **{field: value}), expected_head=HEAD)

    def test_dependency_dag_never_promotes(self):
        stages = {s: "BLOCKED" for s in STAGES}
        result = audit_gate_dependencies(stages)
        self.assertIn("ls5_readonly", result["dependencies_unproven"]["acl_remediation"])
        self.assertFalse(result["execute_authorized"])
        for stage in STAGES:
            stages[stage] = "SYNTHETIC_PASS"
        result = audit_gate_dependencies(stages)
        self.assertFalse(result["deployment_go"])
        self.assertIn("pc4_sid_acl", result["dependencies_unproven"]["limited_pilot"])
        for stage in STAGES:
            stages[stage] = "PHYSICAL_PASS"
        self.assertEqual(audit_gate_dependencies(stages)["status"], "BLOCKED")
        stages["network_preflight"] = "FAIL"
        self.assertEqual(audit_gate_dependencies(stages)["status"], "FAIL")

    def test_four_cell_ci_matrix_and_false_green(self):
        jobs = [
            {"head": HEAD, "os": os_name, "python": version,
             "job_id": i + 1, "conclusion": "success", "tests": 10,
             "failures": 0, "errors": 0, "skipped": 0, "artifact_sha256": "a" * 64}
            for i, (os_name, version) in enumerate(
                (("ubuntu", "3.11"), ("ubuntu", "3.12"),
                 ("windows", "3.11"), ("windows", "3.12")))
        ]
        result = audit_ci_matrix(jobs, expected_head=HEAD)
        self.assertTrue(result["synthetic_matrix_complete"])
        self.assertFalse(result["independent_artifact_bytes_verified"])
        self.assertFalse(result["deployment_go"])
        self.assertFalse(audit_ci_matrix(jobs[:-1], expected_head=HEAD)["synthetic_matrix_complete"])
        for field, value in (("conclusion", "skipped"), ("tests", 0),
                             ("failures", 1), ("errors", 1), ("skipped", 1)):
            bad = [dict(x) for x in jobs]
            bad[0][field] = value
            with self.subTest(field=field):
                self.assertFalse(audit_ci_matrix(bad, expected_head=HEAD)["synthetic_matrix_complete"])
        for bad in ([jobs[0], jobs[0]], [dict(jobs[0], head="f" * 40)],
                    [dict(jobs[0], tests=True)], [dict(jobs[0], os="macos")]):
            with self.subTest(bad=bad), self.assertRaises(AcceptanceBlocked):
                audit_ci_matrix(bad, expected_head=HEAD)

    def test_pending_workflow_is_blocked_not_parser_error(self):
        item = {"name": "preflight", "head": HEAD, "run_id": 42, "attempt": 1,
                "status": "pending", "conclusion": None}
        self.assertFalse(audit_workflow_runs([item], expected_head=HEAD)["offline_ci_complete"])


    def test_rehashed_junit_hidden_text_denied(self):
        original = bundle()
        for modified in (
            original["junit"].replace(b"<testcase ", b"hidden<testcase ", 1),
            original["junit"].replace(b'/>', b'>hidden</testcase>', 1),
            original["junit"].replace(b'/><testcase', b'/>hidden<testcase', 1),
        ):
            altered = dict(original)
            altered["junit"] = modified
            altered["index"] = json.dumps({"head": HEAD, "files": {
                "results.xml": hashlib.sha256(modified).hexdigest(),
                "events.jsonl": hashlib.sha256(altered["jsonl"]).hexdigest()}}).encode()
            with self.subTest(modified=modified), self.assertRaises(AcceptanceBlocked):
                verify_artifacts(**altered)

    def test_cross_pr_g0_g1_fail_closed(self):
        base = "e25197b169ef0e5f37b5bd0030ee4a97b13965e2"
        rows = [
            {"pr": pr, "base": base, "head": HEAD, "draft": True,
             "workflow_conclusion": "queued", "artifact_verified": False,
             "changed_files": [f"scope/{pr}.txt"], "contract_review": False}
            for pr in (238, 239, 240, 241, 242)
        ]
        pins = {row["pr"]: row["head"] for row in rows}
        forged = [dict(row) for row in rows]
        forged[0]["head"] = "f" * 40
        with self.assertRaises(AcceptanceBlocked):
            audit_cross_pr_gates(forged, expected_base=base, expected_heads=pins)
        for bad_pins in (
            {238: HEAD},
            {**pins, 999: HEAD},
            {**pins, 238: "INVALID"},
            {**pins, 238: None},
        ):
            with self.subTest(bad_pins=bad_pins), self.assertRaises(AcceptanceBlocked):
                audit_cross_pr_gates(rows, expected_base=base, expected_heads=bad_pins)
        self.assertEqual(audit_cross_pr_gates(rows, expected_base=base,
                         expected_heads=pins)["status"], "BLOCKED")
        result = audit_cross_pr_gates(rows, expected_base=base)
        self.assertEqual(result["g0_unverified_prs"], [238, 239, 240, 241, 242])
        self.assertFalse(result["combined_behavior_tested"])
        self.assertFalse(result["deployment_go"])
        approved = [dict(x, workflow_conclusion="success",
                         artifact_verified=True, contract_review=True) for x in rows]
        result = audit_cross_pr_gates(approved, expected_base=base)
        self.assertTrue(result["g0_ready_for_review"])
        self.assertTrue(result["g1_contracts_documented"])
        self.assertFalse(result["combined_behavior_tested"])
        overlap = [dict(x) for x in approved]
        overlap[1]["changed_files"] = overlap[0]["changed_files"]
        self.assertTrue(audit_cross_pr_gates(overlap, expected_base=base)["overlapping_files"])
        for changed in ([dict(rows[0], pr=239)], [dict(rows[0], base="f"*40)],
                        [dict(rows[0], draft=False)], [dict(rows[0], changed_files=["../bad"])]):
            with self.subTest(changed=changed), self.assertRaises(AcceptanceBlocked):
                audit_cross_pr_gates(changed, expected_base=base)


if __name__ == "__main__":
    unittest.main()
