"""Actual disposable PostgreSQL transactions; never a physical fleet drill."""
import asyncio,json,os,pathlib,sys,unittest,uuid
sys.path.insert(0,os.environ.get('UNIFIED_SOURCE_ROOT',str(pathlib.Path(__file__).resolve().parents[2]/'unified-system')))
from grid import update_protocol as protocol
from unified_system.release_manifest import canonical

URL=os.environ.get('MISSION3_TEST_DATABASE_URL')


def manifest(version='r1',sequence=1):
    names=('unified-system','grid','strattester','math','meta_analyse','terminan')
    modules={n:dict(version=str(sequence)+'.0.0',commit='a'*40,tree='b'*40,api_major=1,dependencies={},artifact=dict(path='modules/'+n+'.zip',sha256='c'*64,bytes=1),provenance=dict(repository='owner/'+n,run_id='123',attempt=1,workflow_sha='a'*40)) for n in names}
    return canonical(dict(schema='unified.release.v3',release_id=version,sequence=sequence,publisher_sha256='d'*64,modules=modules,execution_authority=False,trading_authorized=False))


@unittest.skipUnless(URL,'explicit disposable Mission3 PostgreSQL URL required')
class RolloutTransactions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from urllib.parse import urlparse
        if urlparse(URL).hostname not in ('localhost','127.0.0.1'):raise ValueError('loopback disposable test DB only')
        import asyncpg
        self.schema='mission3_rollout_'+uuid.uuid4().hex
        self.admin=await asyncpg.connect(URL)
        await self.admin.execute('CREATE SCHEMA '+self.schema)
        self.pool=await asyncpg.create_pool(URL,min_size=2,max_size=4,server_settings={'search_path':self.schema})
        await protocol.ensure_unified_update_schema(self.pool)
        await self.pool.execute("CREATE TABLE service_leases(service_key text PRIMARY KEY,owner text,metadata jsonb,lease_until timestamptz)")
        await self.pool.execute("INSERT INTO service_leases VALUES('control-plane-leader','leader-a','{\"epoch\":1}',now()+interval '10 minutes')")
    async def asyncTearDown(self):
        await self.pool.close();await self.admin.execute('DROP SCHEMA '+self.schema+' CASCADE');await self.admin.close()
    async def guard(self):return dict(owner='leader-a',epoch=1)
    async def begin(self,version='r1',sequence=1):
        return await protocol.begin_unified_rollout(self.pool,manifest(version,sequence),b'CMS',publisher_pin='d'*64,verify_signature=lambda *a:True,node_ids=['lab1','lab2','lab3','lab4','lab5'],canary_node='lab3')
    def health(self,permit):return dict(release_id=permit['version'],release_sha256=permit['manifest_sha256'],ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in json.loads(manifest())['modules'].items()})
    async def test_canary_and_five_node_monotonic_serial_rollout(self):
        await self.begin();seen=[]
        for generation in range(1,6):
            a,b=await asyncio.gather(protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard),protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard))
            permit=a or b;self.assertIsNone(b if a else a)
            self.assertEqual(permit['generation'],generation);seen.append(permit['node_id'])
            await protocol.acknowledge_unified_node(self.pool,permit,healthy=True,lease_guard=self.guard,health=self.health(permit))
            with self.assertRaises(ValueError):await protocol.acknowledge_unified_node(self.pool,permit,healthy=True,lease_guard=self.guard,health=self.health(permit))
        self.assertEqual(seen[0],'lab3');self.assertEqual(len(set(seen)),5)
        self.assertIsNone(await protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard))
        self.assertEqual(await self.pool.fetchval("SELECT status FROM rollout_state WHERE version='r1'"),'complete')
    async def test_stale_lease_timeout_admin_stop_and_immutable_version(self):
        await self.begin()
        with self.assertRaises(ValueError):await self.begin()
        permit=await protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard)
        await self.pool.execute("UPDATE service_leases SET metadata='{\"epoch\":2}'")
        with self.assertRaises(ValueError):await protocol.acknowledge_unified_node(self.pool,permit,healthy=True,lease_guard=self.guard,health=self.health(permit))
        await self.pool.execute("UPDATE service_leases SET metadata='{\"epoch\":1}'")
        await self.pool.execute("UPDATE rollout_nodes SET deadline=now()-interval '1 minute' WHERE status='queued'")
        with self.assertRaises(ValueError):await protocol.acknowledge_unified_node(self.pool,permit,healthy=True,lease_guard=self.guard,health=self.health(permit))
        await protocol.stop_unified_rollout(self.pool,'r1')
        self.assertIsNone(await protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard))
        with self.assertRaises(ValueError):await protocol.start_canary(self.pool,'r1','lab1')
    async def test_dcs_guard_loss_prevents_any_node_claim(self):
        await self.begin()
        async def lost():raise ValueError('DCS lease lost')
        with self.assertRaises(ValueError):await protocol.claim_unified_node(self.pool,'r1',lease_guard=lost)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM rollout_nodes WHERE status='queued'"),0)

    async def test_every_legacy_rollout_entrypoint_cannot_mutate_v3(self):
        from grid import rollout
        await self.begin();permit=await protocol.claim_unified_node(self.pool,'r1',lease_guard=self.guard)
        before=await self.pool.fetchrow("SELECT phase,status,generation FROM rollout_state WHERE version='r1'")
        with self.assertRaises(ValueError):await rollout.begin_stable_rollout(self.pool,'r1',['lab1','lab2'],'lab1')
        with self.assertRaises(ValueError):await rollout.launch_next_wave(self.pool,'r1')
        good=dict(integrity_ok=True,pressure_state='NORMAL',db_write_failures=0,db_queue_ratio=0.,db_spool_ratio=0.)
        with self.assertRaises(ValueError):await rollout.note_rollout_heartbeat(self.pool,permit['node_id'],'r1',heartbeat=good)
        await self.pool.execute("UPDATE rollout_nodes SET deadline=now()-interval '1 minute' WHERE status='queued'")
        self.assertEqual(await rollout.expire_rollout_nodes(self.pool),[])
        after=await self.pool.fetchrow("SELECT phase,status,generation FROM rollout_state WHERE version='r1'")
        self.assertEqual(dict(before),dict(after))
        self.assertEqual(await self.pool.fetchval("SELECT status FROM rollout_nodes WHERE status='queued'"),'queued')
        await protocol.register_release(self.pool,'r1','stable','https://bad.invalid','f'*64,{})
        self.assertEqual(await self.pool.fetchval("SELECT metadata->>'schema' FROM agent_releases WHERE version='r1'"),'grid.unified.release.v3')
