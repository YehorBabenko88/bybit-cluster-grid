"""SOURCE/PREPARATION structural/local tests. NEVER send native RPC."""
import ast,inspect,socket,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import httpx
from unified_system.journal import Journal
from grid.coordination import ConsulConfig,ConsulSessionAuthority
from grid.authority_runtime_v1 import canonical,measure_native_plan
from grid import authority_assignment_v1 as native

class CommissionerPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='a2-commissioner-source-');self.addCleanup(self.temp.cleanup)
        self.intent=dict(schema='unified.authority.unqualified-worker-registration-intent.v1-review1',operation='COMMISSION_UNQUALIFIED_WORKER',
            cluster_id=str(uuid.uuid4()),cluster_generation=str(uuid.uuid4()),realm_id=str(uuid.uuid4()),node_id=str(uuid.uuid4()),
            worker_inventory_incarnation_id=str(uuid.uuid4()),worker_module_sha256='a'*64,original_registration_request_id=str(uuid.uuid4()))
        self.raw=canonical(self.intent)
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.addCleanup(self.socket.close)
        endpoint='http://127.0.0.1:'+str(self.socket.getsockname()[1])
        self.config=ConsulConfig((endpoint,),'unified/'+self.intent['cluster_id'],isolated_lab=True,acl_token='UNISSUED_FORMAT_TEST_TOKEN')
        self.authority=ConsulSessionAuthority(self.config);self.addAsyncCleanup(self.authority.close)
        self.custody=native.RootRegistrationCustody(Journal(Path(self.temp.name)/'registration.sqlite'),original_intent_bytes=self.raw)
        self.addCleanup(self.custody.close)
    def make(self,authority=None):
        return native.UnqualifiedWorkerCommissioner(self.authority if authority is None else authority,
            self.intent['cluster_generation'],self.intent['realm_id'],root_custody=self.custody)
    async def test_public_execution_gate_closed_before_any_rpc_or_attempt(self):
        source=self.make()
        with patch.object(self.authority.client,'send',side_effect=AssertionError('NATIVE_RPC_FORBIDDEN_IN_PREPARATION')) as send:
            for operation in (source.commission_unqualified_worker,source.reconcile_unqualified_worker):
                with self.assertRaisesRegex(native.RegistrationCustodyUnavailable,'SOURCE_PREPARATION_ONLY_EXECUTION_GATE_CLOSED'):
                    await operation(self.raw,leader=None)
            send.assert_not_called()
        self.assertEqual(Journal(self.custody._path).read(),[])
    async def test_injected_client_and_nonliteral_endpoint_refused_locally(self):
        injected=httpx.AsyncClient(trust_env=False);self.addAsyncCleanup(injected.aclose)
        other=ConsulSessionAuthority(self.config,client=injected)
        with self.assertRaises(native.RegistrationCustodyUnavailable):self.make(other)
        remote=ConsulSessionAuthority(ConsulConfig(('http://localhost:8500',),self.config.namespace,isolated_lab=True,acl_token='UNISSUED'))
        self.addAsyncCleanup(remote.close)
        with self.assertRaises(native.RegistrationCustodyUnavailable):self.make(remote)
    async def test_rebound_closed_or_wrong_original_never_reaches_send(self):
        source=self.make();original=self.authority.client
        replacement=httpx.AsyncClient(trust_env=False);self.addAsyncCleanup(replacement.aclose)
        self.authority.client=replacement
        try:
            with self.assertRaises(native.RegistrationCustodyUnavailable):await source.commission_unqualified_worker(self.raw,leader=None)
        finally:self.authority.client=original
        await original.aclose()
        with self.assertRaises(native.RegistrationCustodyUnavailable):await source.reconcile_unqualified_worker(self.raw,leader=None)
    async def test_private_record_builder_is_unissued_closed_metadata_only(self):
        source=self.make();record=source._record('12345678-1234-1234-9234-123456789abc')
        self.assertEqual(len(record),14);self.assertEqual(record['registration_state'],'UNQUALIFIED')
        self.assertEqual(record['admitted_fields'],[]);self.assertIs(record['resources_reserved'],False);self.assertIs(record['effect_permitted'],False)
        self.assertNotIn('operation',record);self.assertEqual(record['worker_inventory_incarnation_id'],self.intent['worker_inventory_incarnation_id'])
    async def test_sender_has_one_stream_site_and_no_core_retry_wrapper(self):
        source=inspect.getsource(native.UnqualifiedWorkerCommissioner)
        tree=ast.parse(source)
        streams=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='stream']
        self.assertEqual(len(streams),1)
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr=='_request' for n in ast.walk(tree)))
        self.assertTrue(any(k.arg=='follow_redirects' and isinstance(k.value,ast.Constant) and k.value.value is False for k in streams[0].keywords))

if __name__=='__main__':unittest.main()
