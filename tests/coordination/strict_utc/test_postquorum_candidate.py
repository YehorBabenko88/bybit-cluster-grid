"""Pure bounded hypothesis tests. No clock/key/native witness exists here."""
import importlib.util
from pathlib import Path
import sys
import unittest


class PostQuorumCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).parents[3]/'docs/coordination/strict-utc/postquorum_candidate.py'
        spec=importlib.util.spec_from_file_location('postquorum_utc_candidate_model',p)
        cls.m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cls.m
        spec.loader.exec_module(cls.m)

    def case(self,**kw):
        return self.m.Case(**dict(expiry=10,commit_event=2,witness_sample=3,
            witness_upper=4,proof_delivery=5,entry_term=7,commit_term=7,
            witness_term=7,**kw))

    def test_causal_verified_upper_proves_only_prior_commit_bound(self):
        x=self.case()
        self.assertEqual(x.time_claim(),'CONDITIONAL_BEFORE_EXPIRY')
        self.assertNotEqual(x.commit_event,x.witness_upper)
        self.assertFalse(x.strict_native_enforcement_available())

    def test_after_commit_certificate_cannot_prevent_late_native_mutation(self):
        x=self.m.Case(expiry=10,commit_event=12,witness_sample=13,
            witness_upper=14,proof_delivery=15,entry_term=7,commit_term=7,witness_term=7)
        self.assertTrue(x.native_mutation_already_committed)
        self.assertEqual(x.time_claim(),'UNKNOWN')
        self.assertFalse(x.strict_native_enforcement_available())

    def test_early_commit_late_sampling_is_unknown_not_late_commit_proof(self):
        x=self.m.Case(expiry=10,commit_event=2,witness_sample=13,
            witness_upper=14,proof_delivery=15,entry_term=7,commit_term=7,witness_term=7)
        self.assertEqual(x.time_claim(),'UNKNOWN')
        self.assertLess(x.commit_event,x.expiry)

    def test_early_bound_delivered_late_remains_historical_only(self):
        x=self.m.Case(expiry=10,commit_event=2,witness_sample=3,
            witness_upper=4,proof_delivery=15,entry_term=7,commit_term=7,witness_term=7)
        self.assertEqual(x.time_claim(),'CONDITIONAL_BEFORE_EXPIRY')
        self.assertFalse(x.current_effect_eligibility())

    def test_old_term_and_changed_term_are_outside_direct_candidate(self):
        for entry,commit,witness in [(6,7,7),(7,7,8)]:
            with self.subTest(entry=entry,commit=commit,witness=witness):
                x=self.m.Case(expiry=10,commit_event=2,witness_sample=3,
                    witness_upper=4,proof_delivery=5,entry_term=entry,
                    commit_term=commit,witness_term=witness)
                self.assertEqual(x.time_claim(),'UNKNOWN')

    def test_unqualified_or_mismatched_witness_is_unknown(self):
        for field in ('utc_bound_valid','causal_hook_valid','binding_valid','durable_quorum_valid'):
            with self.subTest(field=field):
                args=dict(expiry=10,commit_event=2,witness_sample=3,witness_upper=4,
                    proof_delivery=5,entry_term=7,commit_term=7,witness_term=7)
                args[field]=False
                self.assertEqual(self.m.Case(**args).time_claim(),'UNKNOWN')

    def test_equal_expiry_and_precommit_sample_do_not_prove(self):
        for sample,upper in [(3,10),(1,4),(3,2)]:
            with self.subTest(sample=sample,upper=upper):
                x=self.m.Case(expiry=10,commit_event=2,witness_sample=sample,
                    witness_upper=upper,proof_delivery=15,entry_term=7,commit_term=7,witness_term=7)
                self.assertEqual(x.time_claim(),'UNKNOWN')

    def test_model_never_issues_effect_or_actual_capability(self):
        for x in (self.case(),self.m.late_counterexample()):
            self.assertFalse(x.current_effect_eligibility())
            self.assertFalse(x.report()['actual_clock_certificate_issued'])
            self.assertFalse(x.report()['native_enforcement_implemented'])


if __name__=='__main__':unittest.main()
