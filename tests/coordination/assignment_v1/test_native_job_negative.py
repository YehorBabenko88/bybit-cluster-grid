"""Actual broker/Consul negative composition; never seed issued job records."""
import hashlib,unittest
import test_native_profile_v2 as profile_fixture
from unified_system.gateway_research_identity import ResearchIdentityDenied
from grid.coordination import CoordinationUnavailable
from grid import authority_assignment_v1 as native

class NativeJobNegativeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):profile_fixture.NativeProfileV2Tests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):profile_fixture.NativeProfileV2Tests.tearDownClass.__func__(cls)
    put=profile_fixture.NativeProfileV2Tests.put
    commission=profile_fixture.NativeProfileV2Tests.commission
    rebind_target=profile_fixture.NativeProfileV2Tests.rebind_target
    submit=profile_fixture.NativeProfileV2Tests.submit
    async def asyncSetUp(self):
        await profile_fixture.NativeProfileV2Tests.asyncSetUp(self)
        self.context=await self.broker.open_session(self.tls.accepted,leader=self.leader)
        self.raw=profile_fixture.canonical(self.submit())
        self.handler=native.ResearchLabAuthority(self.authority,self.generation,broker=self.broker)
    async def test_actual_authenticated_submit_denies_unqualified_resources_without_job(self):
        result=await self.handler.submit(self.raw,context=self.context,leader=self.leader)
        self.assertIs(type(result),native.ResearchAdmissionResult)
        self.assertEqual(result.outcome,'DENIED')
        self.assertEqual(result.reason,'NATIVE_WORKER_RESOURCE_API_UNQUALIFIED')
        self.assertEqual(result.original_intent_sha256,hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result.commit_status,'NOT_ATTEMPTED');self.assertIs(result.effect_permitted,False)
        again=await self.handler.submit(self.raw,context=self.context,leader=self.leader)
        self.assertEqual(again,result)
        lookup=await self.handler.lookup(self.raw,context=self.context)
        self.assertEqual(lookup.outcome,'UNKNOWN');self.assertIs(lookup.effect_permitted,False)
        self.assertIsNone(await self.authority._request('GET','/v1/kv/'+self.prefix+'jobs/'+self.job,params={'consistent':''},missing_ok=True))
    async def test_fake_context_and_changed_original_cannot_reach_resource_gate(self):
        with self.assertRaises(ResearchIdentityDenied):await self.handler.submit(self.raw,context=object(),leader=self.leader)
        with self.assertRaises((ResearchIdentityDenied,ValueError)):
            await self.handler.submit(b'{}',context=self.context,leader=self.leader)
    async def test_actual_destroyed_leader_cannot_reach_resource_gate(self):
        await self.authority._request('PUT','/v1/session/destroy/'+self.leader.session_id)
        with self.assertRaises(native.AssignmentUnavailable):await self.handler.submit(self.raw,context=self.context,leader=self.leader)
    async def test_actual_revoked_current_policy_never_reaches_resource_gate(self):
        await self.put(self.prefix+'policies/'+self.policy,dict(self.policy_body,state='REVOKED',revision='2'))
        with self.assertRaises(ResearchIdentityDenied):await self.handler.submit(self.raw,context=self.context,leader=self.leader)
    async def test_z_actual_no_quorum_never_returns_gate_or_cached_job_observation(self):
        await self.handler.lookup(self.raw,context=self.context)
        for process in self.lab.processes[1:]:process.kill();process.wait(timeout=10)
        with self.assertRaises((CoordinationUnavailable,native.AssignmentUnavailable)):
            await self.handler.submit(self.raw,context=self.context,leader=self.leader)

if __name__=='__main__':unittest.main()
