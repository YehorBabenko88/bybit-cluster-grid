"""Deterministic countermodel tests ONLY; no Grid/Consul/worker imports or calls."""
import importlib.util
from pathlib import Path
import sys
import unittest


class StrictUTCModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).parents[3]/'docs/coordination/strict-utc/countermodel.py'
        spec=importlib.util.spec_from_file_location('strict_utc_countermodel',path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        cls.model=module

    def test_identical_observations_straddle_expiry(self):
        early,late=self.model.indistinguishable_pair()
        self.assertEqual(early.client_observations(),late.client_observations())
        self.assertTrue(early.committed_before_expiry)
        self.assertFalse(late.committed_before_expiry)
        self.assertTrue(early.native_predicates_accept)
        self.assertTrue(late.native_predicates_accept)

    def test_postcheck_denial_cannot_erase_known_commit(self):
        early,late=self.model.indistinguishable_pair()
        for execution in (early,late):
            self.assertFalse(execution.reader_current_at_response)
            self.assertTrue(execution.native_committed)
            self.assertEqual(execution.public_observation(),{'status':'UNAVAILABLE'})
            self.assertEqual(execution.private_fact(),'COMMITTED_TIME_UNKNOWN')

    def test_boundary_equality_is_not_before_expiry(self):
        case=self.model.Execution(expiry=5,precheck=1,commit=5,apply=5,response=7,session_invalidated=10)
        self.assertTrue(case.native_predicates_accept)
        self.assertFalse(case.committed_before_expiry)

    def test_native_revocation_order_can_reject_but_is_not_utc_deadline(self):
        late=self.model.Execution(expiry=5,precheck=1,commit=6,apply=6,response=7,session_invalidated=4)
        self.assertFalse(late.native_predicates_accept)
        self.assertFalse(late.native_committed)
        # A delayed revoke is consistent with TTL's lack of an upper bound.
        delayed=self.model.Execution(expiry=5,precheck=1,commit=6,apply=6,response=7,session_invalidated=10)
        self.assertTrue(delayed.native_committed)
        self.assertFalse(delayed.committed_before_expiry)

    def test_every_last_precheck_has_a_later_crossing_schedule(self):
        for remaining in (1,2,10,2500):
            with self.subTest(remaining=remaining):
                expiry=10000
                case=self.model.Execution(expiry=expiry,precheck=expiry-remaining,
                    commit=expiry+1,apply=expiry+2,response=expiry+3,session_invalidated=expiry+10)
                self.assertTrue(case.client_precheck_accepts)
                self.assertTrue(case.native_committed)
                self.assertFalse(case.committed_before_expiry)

    def test_ack_apply_or_supplied_field_is_not_commit_instant(self):
        early,late=self.model.indistinguishable_pair()
        self.assertEqual(early.response,late.response)
        self.assertEqual(early.apply,late.apply)
        self.assertNotEqual(early.commit,late.commit)
        self.assertIsNone(early.report()['observed_commit_utc'])
        self.assertIsNone(late.report()['observed_commit_utc'])

    def test_fail_closed_mode_has_no_native_send(self):
        result=self.model.disabled_contract()
        self.assertEqual(result['logical_mutations'],'DISABLED')
        self.assertEqual(result['native_sends'],0)
        self.assertFalse(result['strict_positive_admission_available'])


if __name__=='__main__':unittest.main()
