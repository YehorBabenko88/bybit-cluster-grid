import unittest
from audit.integration_ci.workflow_attestation import assess
from audit.integration_ci.evidence_manifest import validate_manifest, CRITICAL
from audit.integration_ci.cross_contracts import inspect_contracts
from audit.integration_ci.evidence_gate import validate

SHA = 'a' * 40

class IntegrationBoundaryTests(unittest.TestCase):
    def test_required_coverage_cannot_be_disabled(self):
        self.assertEqual(assess([], SHA, required=frozenset())['status'], 'BLOCKED_UNPROVEN')

    def test_nonhex_sha_rejected(self):
        bad = 'z' * 40
        runs = [dict(name=n, head_sha=bad, status='completed', conclusion='success') for n in CRITICAL]
        self.assertEqual(assess(runs, bad)['status'], 'BLOCKED_UNPROVEN')
        self.assertTrue(validate_manifest(dict(commit_sha=bad, required_workflows=sorted(CRITICAL), source='github-actions', synthetic=False), bad))

    def test_invalid_attestation_keeps_denials(self):
        result = assess(None, SHA)
        self.assertIs(result.get('readiness_passed'), False)
        self.assertIs(result.get('execution_authorized'), False)

    def test_unhashable_run_name_fails_closed(self):
        self.assertEqual(assess([{'name': []}], SHA)['status'], 'BLOCKED_UNPROVEN')

    def test_missing_or_nonstring_sessions_rejected(self):
        for session in (None, '', [], 1):
            vm = dict(mode='PlanOnly', physical_cases_status='NOT_RUN', ownership_session=session)
            pg = dict(mode='read-only', schema_version=1, ownership_session=session)
            att = dict(authenticated=True, session=session, readiness_passed=False, execution_authorized=False)
            self.assertTrue(inspect_contracts(vm, pg, att))

    def test_unhashable_vm_identifier_fails_closed(self):
        data = dict(status='BLOCKED_UNPROVEN', readiness_passed=False, execution_authorized=False, schema_2_enabled=False,
                    vm_cases=[dict(id=[i], status='NOT_RUN') for i in range(12)])
        self.assertTrue(validate(data))

    def test_unsafe_path_aliases_rejected(self):
        from audit.integration_ci.branch_overlap import collisions
        for path in ('x\\..\\secret', 'C:/secret', 'x//y', './x', 'x\x00y'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                collisions({'a': [path]})
