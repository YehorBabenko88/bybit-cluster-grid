"""Real consistent native read substrate; probe rows are NOT issued job proof."""
import asyncio,json,os,tempfile,time,unittest,uuid
from pathlib import Path
from grid.coordination import ConsulConfig,ConsulSessionAuthority,CoordinationLost,CoordinationUnavailable
from grid.authority_runtime_v1 import canonical
from grid.authority_assignment_v1 import AssignmentAuthority,AssignmentUnavailable,_check,_cas
from native_snapshot_consul_lab import ConsulLab

class NativeSnapshotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='a2-native-snapshot-')
        binary=os.environ.get('A2_NATIVE_CONSUL_BINARY','C:/Users/LS-5/Documents/Codex/2026-11-06/codex-agent-8-independent-security-ci/work/consul-bin/extracted/consul.exe')
        cls.lab=ConsulLab(binary,Path(cls.temp.name)/'consul')
        try:cls.lab.__enter__()
        except BaseException:cls.temp.cleanup();raise
    @classmethod
    def tearDownClass(cls):cls.lab.__exit__(None,None,None);cls.temp.cleanup()
    async def asyncSetUp(self):
        self.cluster=str(uuid.uuid4());self.generation=str(uuid.uuid4())
        self.authority=ConsulSessionAuthority(ConsulConfig(tuple(self.lab.nodes),'unified/'+self.cluster,isolated_lab=True,acl_token=self.lab.token,ttl_seconds=15,request_timeout=2))
        self.addAsyncCleanup(self.authority.close)
        self.backend=AssignmentAuthority(self.authority,self.generation)
        self.prefix=self.authority.config.namespace+'/runtime-v1/probe-only/snapshot/'
        self.a=self.prefix+'a';self.b=self.prefix+'b';self.missing=self.prefix+'not-written'
        for key,value in ((self.a,'one'),(self.b,'two')):
            self.assertIs(await self.authority._request('PUT','/v1/kv/'+key,content=canonical(dict(schema='untrusted.native-snapshot-probe.v1',value=value))),True)
    async def test_00_actual_atomic_existing_and_absent_snapshot(self):
        # Observe actual server semantics; never inject a transport response.
        native=await self.authority._request('PUT','/v1/txn',params={'consistent':''},json=[{'KV':dict(Verb='get-or-empty',Key=k)} for k in (self.a,self.missing)])
        print(json.dumps(dict(scope='ACTUAL_UNTRUSTED_PROBE_GET_OR_EMPTY_RESPONSE',response=native)),flush=True)
        rows=await self.backend._read_snapshot((self.a,self.missing,self.b))
        self.assertEqual(len(rows),3);self.assertEqual(tuple(r.key for r in rows),(self.a,self.missing,self.b))
        self.assertEqual(json.loads(rows[0].raw)['value'],'one');self.assertGreater(rows[0].index,0)
        self.assertIsNone(rows[1].raw);self.assertEqual(rows[1].index,0)
        self.assertEqual(json.loads(rows[2].raw)['value'],'two');self.assertGreater(rows[2].index,0)
        with self.assertRaises(AssignmentUnavailable):await self.backend.execute(b'{}',context=object(),leader=None)
    async def test_actual_stale_snapshot_cas_rolls_back_without_probe_effect(self):
        old=await self.backend._read_snapshot((self.a,self.b))
        await self.authority._request('PUT','/v1/kv/'+self.a,content=canonical(dict(schema='untrusted.native-snapshot-probe.v1',value='changed')))
        effect=self.prefix+'must-remain-absent'
        with self.assertRaises(CoordinationLost):
            await self.backend._transaction([_check(r) for r in old]+[_cas(effect,0,dict(schema='untrusted.probe-effect.v1'))])
        self.assertEqual((await self.backend._read_snapshot((effect,)))[0].index,0)
    async def test_actual_acl_denial_never_becomes_absence(self):
        policy=await self.authority._request('PUT','/v1/acl/policy',json=dict(Name='snapshot-'+str(uuid.uuid4()),Rules='key_prefix "'+self.a+'" { policy = "read" }'))
        token=await self.authority._request('PUT','/v1/acl/token',json=dict(Description='owned-snapshot-negative',Policies=[dict(ID=policy['ID'])]))
        try:
            restricted=ConsulSessionAuthority(ConsulConfig(tuple(self.lab.nodes),self.authority.config.namespace,isolated_lab=True,acl_token=token['SecretID'],request_timeout=2))
            try:
                backend=AssignmentAuthority(restricted,self.generation)
                with self.assertRaises((AssignmentUnavailable,CoordinationUnavailable)):
                    await backend._read_snapshot((self.a,self.b))
            finally:await restricted.close()
        finally:
            await self.authority._request('DELETE','/v1/acl/token/'+token['AccessorID'])
            await self.authority._request('DELETE','/v1/acl/policy/'+policy['ID'])
    async def test_actual_all_node_restart_retains_raw_snapshot_indices(self):
        before=await self.backend._read_snapshot((self.a,self.b,self.missing))
        await asyncio.to_thread(self.lab.restart_all)
        self.assertEqual(await self.backend._read_snapshot((self.a,self.b,self.missing)),before)
    async def test_actual_leader_failure_two_voters_keep_snapshot(self):
        before=await self.backend._read_snapshot((self.a,self.b))
        configuration=await self.authority._request('GET','/v1/operator/raft/configuration',params={'consistent':''})
        leader=next(row for row in configuration['Servers'] if row['Leader'])
        index=int(leader['Node'].rsplit('-',1)[1]);owned=self.lab.processes[index]
        owned.kill();owned.wait(timeout=10)
        try:
            deadline=time.monotonic()+15
            while True:
                try:after=await self.backend._read_snapshot((self.a,self.b));break
                except CoordinationUnavailable:
                    if time.monotonic()>=deadline:raise
                    await asyncio.sleep(.2)
            self.assertEqual(after,before)
            self.assertEqual(sum(p.poll() is None for p in self.lab.processes),2)
        finally:await asyncio.to_thread(self.lab.restart_all)
    async def test_snapshot_rejects_duplicate_outside_namespace_and_overflow(self):
        for keys in ((self.a,self.a),(),[self.a],('unified/foreign/probe',),(self.prefix+'../other',),tuple(self.prefix+str(i) for i in range(65))):
            with self.subTest(keys_type=type(keys).__name__),self.assertRaises(ValueError):await self.backend._read_snapshot(keys)
    async def test_z_actual_one_of_three_no_quorum_never_returns_cached_snapshot(self):
        await self.backend._read_snapshot((self.a,))
        for process in self.lab.processes[1:]:process.kill();process.wait(timeout=10)
        with self.assertRaises(CoordinationUnavailable):await self.backend._read_snapshot((self.a,))

if __name__=='__main__':unittest.main()
