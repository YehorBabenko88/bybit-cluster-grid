"""Executable negative contracts for the absent native Assignment backend.
No models/booleans here establish native identity or dispatch permission.
"""
import asyncio,unittest,uuid
from grid.authority_runtime_v1 import PartitionIdentity
from grid.authority_assignment_v1 import AssignmentAuthority,AssignmentLayout,AssignmentUnavailable

def uid():return str(uuid.uuid4())
class AssignmentContractTests(unittest.TestCase):
    def setUp(self):self.cluster,self.generation,self.dataset=uid(),uid(),uid()
    def test_new_layout_preserves_stable_partition_key_and_rejects_unsafe_original(self):
        layout=AssignmentLayout(PartitionIdentity(self.cluster,self.dataset,'source','partition'))
        for request in ('../other','x/y','',True,uid().upper()):
            with self.assertRaises(ValueError):layout.original(request,'a'*64,uid())
    def test_distinct_storage_records_do_not_alias_issuance_lifecycle_policy_accounting(self):
        layout=AssignmentLayout(PartitionIdentity(self.cluster,self.dataset,'source','partition'))
        node,volume,instance,reservation,policy,basis=[uid() for _ in range(6)]
        keys=layout.storage_binding(node,volume,instance,reservation,policy,basis,policy_revision='23',basis_revision='17')
        self.assertEqual(set(keys),{'issuance','lifecycle','policy','accounting','budget_basis'})
        self.assertEqual(len(set(keys.values())),5)
    def test_default_missing_actual_native_provider_never_touches_consul(self):
        class UnusedAuthority:
            class config:namespace='unified/'+self.cluster
            async def _request(self,*args,**kwargs):raise AssertionError('NATIVE_GATE_BYPASSED')
        backend=AssignmentAuthority(UnusedAuthority(),self.generation)
        with self.assertRaises(AssignmentUnavailable):asyncio.run(backend.execute(b'{}',context=object(),leader=None))
    def test_none_boolean_shape_is_not_a_native_provider(self):
        for provider in (True,False,{},object()):
            with self.assertRaises((TypeError,AssignmentUnavailable)):
                AssignmentAuthority(None,self.generation,native_provider=provider)
    def test_native_plan_overflow_is_rejected_before_transport(self):
        class UnusedAuthority:
            async def _request(self,*args,**kwargs):raise AssertionError('OVERFLOW_REACHED_TRANSPORT')
        backend=AssignmentAuthority(UnusedAuthority(),self.generation)
        with self.assertRaises(ValueError):asyncio.run(backend._transaction([{'KV':{'Verb':'check-not-exists','Key':'probe'}}]*65))
    def test_deep_or_noncanonical_native_record_is_rejected(self):
        from grid.authority_assignment_v1 import _decode
        for raw in (b'{"x":1}',b'{"x":"a","x":"b"}',b'{ "x":"a"}',b'{"x":'+b'['*13+b'null'+b']'*13+b'}'):
            with self.assertRaises(ValueError):_decode(raw)
    def test_malformed_native_success_response_is_not_commit_confirmation(self):
        class Malformed:
            async def _request(self,*args,**kwargs):return {}
        backend=AssignmentAuthority(Malformed(),self.generation)
        with self.assertRaises(AssignmentUnavailable):asyncio.run(backend._transaction([{'KV':{'Verb':'check-not-exists','Key':'probe'}}]))
if __name__=='__main__':unittest.main()
