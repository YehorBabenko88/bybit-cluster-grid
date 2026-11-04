"""Actual disposable PostgreSQL contract; no local/office DB is selected."""
import asyncio,copy,json,os,re,uuid
import asyncpg,pytest
from grid.data_first_jobs import enqueue,publish as server_publish,request_sha,SCHEMA,KIND
from grid.ml_transport import claim_data_first
from grid.ml_worker_protocol import accept_assigned_job
from tests.test_data_first_jobs import request

def _disposable_dsn(environ):
 # Private DDL is enabled only in the reviewed ephemeral service job, never by
 # an ambient DSN alone. Unit guard tests do not establish a DB connection.
 fixed='postgresql://grid:grid@127.0.0.1:5432/grid'
 expected={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_REPOSITORY':'YehorBabenko88/bybit-cluster-grid','GITHUB_JOB':'linux-postgres18','HISTORY_DISPOSABLE_DSN':fixed,'MISSION3_TEST_DATABASE_URL':fixed}
 if any(environ.get(key)!=value for key,value in expected.items()):raise ValueError('DISPOSABLE_PG_JOB_REQUIRED')
 return fixed

def _private_schema(value):
 if type(value) is not str or re.fullmatch(r'data_first_(?:test|yield)_[a-f0-9]{32}',value) is None:raise ValueError('PRIVATE_SCHEMA_REQUIRED')
 return value

async def _public_objects(connection):
 return [tuple(row) for row in await connection.fetch("SELECT c.oid::bigint,c.relname,c.relkind FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid")]


pytestmark=pytest.mark.skipif(not os.environ.get('HISTORY_DISPOSABLE_DSN'),reason='actual disposable PostgreSQL unavailable; NOT_RUN')

def test_real_authority_permanent_dedupe_typed_claim_and_fenced_publication(tmp_path,monkeypatch):
 async def scenario():
  dsn=_disposable_dsn(os.environ);schema=_private_schema('data_first_test_'+uuid.uuid4().hex)
  admin=await asyncpg.connect(dsn,server_settings={'search_path':'pg_catalog'});pool=None;created=False
  public_before=None
  try:
   public_before=await _public_objects(admin)
   await admin.execute(f'CREATE SCHEMA "{schema}"');created=True
   await admin.execute(f'''CREATE TABLE "{schema}".ml_jobs(id uuid PRIMARY KEY,job_type text NOT NULL,payload jsonb NOT NULL,dedupe_key text,status text NOT NULL DEFAULT 'queued',priority integer NOT NULL DEFAULT 1,created_at timestamptz DEFAULT clock_timestamp(),lease_owner text,lease_until timestamptz,started_at timestamptz,finished_at timestamptz,attempts integer DEFAULT 0,max_attempts integer DEFAULT 3,not_before timestamptz,error text,lease_generation bigint DEFAULT 0)''')
   await admin.execute(f'CREATE TABLE "{schema}".ml_resource_reservations(job_id uuid PRIMARY KEY,expires_at timestamptz)')
   async def setup(c):
    await c.execute(f'SET search_path TO "{schema}"')
    assert await c.fetchval('SELECT current_schema()')==schema
   pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,setup=setup)
   for _ in range(3):
    async with pool.acquire() as connection:assert await connection.fetchval('SELECT current_schema()')==schema
   from grid.migrations import MIGRATIONS
   for version,name,sqls in MIGRATIONS:
    if version in (12,13,14,48):
     for sql in sqls:await pool.execute(sql)
   a=request();policy={'a'*40:['b'*64]};ident=await enqueue(pool,a,policy)
   async def publish(*args):return await server_publish(*args,request_pin=request_sha(a))
   assert await enqueue(pool,a,policy)==ident
   conflicting=copy.deepcopy(a);conflicting['resources']['cpu']=2.
   with pytest.raises(ValueError):await enqueue(pool,conflicting,policy)
   from grid.ml_concurrency import claim_ml_job
   assert await claim_ml_job(pool,'legacy') is None
   await pool.execute("UPDATE ml_jobs SET status='assigned',lease_owner='node',lease_until=clock_timestamp()+interval '120 seconds' WHERE id=$1",uuid.UUID(ident))
   assert await accept_assigned_job(pool,'node') is None
   assert await claim_data_first(pool,'node',None,{'data_first_runtime':{'protocol':SCHEMA,'source_commit':'a'*40}}) is None
   job=await claim_data_first(pool,'node',policy,{'data_first_runtime':{'protocol':SCHEMA,'source_commit':'a'*40}})
   assert job['job_type']==KIND and job['lease_generation']==1 and job['payload']==a
   # A genuine current DataFirst generation cannot use any train publication
   # path. Missing dataset_id is not the guard: kind is rejected at SQL entry.
   from grid import ml_transport as transport
   from grid.ml_worker_protocol import complete_running_job,fail_running_job
   import hashlib
   writes=[]
   class Store:
    def put_bytes(self,data):
     writes.append(bytes(data));(tmp_path/'model.bin').write_bytes(data)
     return dict(id=uuid.uuid4(),storage_uri='artifact://fixture/model',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   store=Store();jid=uuid.UUID(ident)
   from grid.ml_training_worker import TrainingWorker,StaleTrainingLease
   dataset_id=uuid.uuid4();worker=TrainingWorker(pool,object(),'source-fixture')
   await pool.execute("INSERT INTO dataset_snapshots(id,purpose,cutoff_ts,created_by,status,feature_version) VALUES($1,'fixture',clock_timestamp(),'fixture','READY','v1')",dataset_id)
   with pytest.raises(StaleTrainingLease):
    await worker._publish_candidate(uuid.uuid4(),'global',dataset_id,uuid.uuid4(),'v1',{},job_id=jid,lease_owner='node',lease_generation=1)
   assert await transport.train_lease_valid(pool,jid,'node',1) is False
   assert await transport.dataset_page(pool,jid,'node',1) is None
   assert await transport.publish_artifact(pool,store,jid,'node',1,b'model',hashlib.sha256(b'model').hexdigest()) is None
   assert await transport.register_saved_artifact(pool,jid,'node',1,dict(id=uuid.uuid4(),storage_uri='artifact://fixture',bytes=5,sha256='c'*64)) is None
   assert await transport.finalize_model(pool,jid,'node',1,uuid.uuid4()) is False
   assert await complete_running_job(pool,jid,'node',1) is False
   assert await fail_running_job(pool,jid,'node',1,ValueError('fixture'))=='stale'
   assert await transport.renew(pool,jid,'node',1) is True
   assert writes==[] and not (tmp_path/'model.bin').exists()
   from grid import coordinator as control
   from fastapi import HTTPException
   from types import SimpleNamespace
   async def authenticated(*args):pass
   def no_store(*args):raise AssertionError('DataFirst stream created artifact store')
   class Stream:
    headers={}
    async def stream(self):raise AssertionError('DataFirst stream consumed');yield b''
   with monkeypatch.context() as patch:
    patch.setattr(control,'db',SimpleNamespace(pool=pool));patch.setattr(control,'node_auth',authenticated);patch.setattr(control,'LocalArtifactStore',no_store)
    with pytest.raises(HTTPException) as blocked:await control.upload_ml_artifact(ident,Stream(),'node',1,'c'*64)
    assert blocked.value.status_code==409
   assert await pool.fetchval('SELECT count(*) FROM ml_artifacts')==0
   assert await pool.fetchval('SELECT count(*) FROM model_registry')==0
   assert await pool.fetchval('SELECT count(*) FROM model_evaluations')==0
   assert await pool.fetchval('SELECT status FROM ml_jobs WHERE id=$1',jid)=='running'
   # Positive train control verifies typed guards still permit the old route.
   train_id=uuid.uuid4()
   await pool.execute("INSERT INTO ml_jobs(id,job_type,payload,status,lease_owner,lease_until,lease_generation) VALUES($1,'train','{}'::jsonb,'running','train-node',clock_timestamp()+interval '120 seconds',1)",train_id)
   assert await transport.train_lease_valid(pool,train_id,'train-node',1) is True
   saved_model=await transport.publish_artifact(pool,store,train_id,'train-node',1,b'model',hashlib.sha256(b'model').hexdigest());assert saved_model
   await worker._publish_candidate(uuid.uuid4(),'global',dataset_id,uuid.UUID(saved_model['artifact_id']),'v1',{},job_id=train_id,lease_owner='train-node',lease_generation=1)
   assert await pool.fetchval('SELECT count(*) FROM model_registry')==1
   assert writes==[b'model'] and await pool.fetchval('SELECT count(*) FROM ml_artifacts')==1
   await pool.execute('DELETE FROM ml_artifacts');await pool.execute('DELETE FROM ml_jobs WHERE id=$1',train_id)
   assert await publish(pool,ident,'node',2,1,'RUNNING',{},policy) is None
   first=await publish(pool,ident,'node',1,1,'RUNNING',{'reason':'','progress':{'input_sha256':'c'*64}},policy);assert first['accepted']
   await pool.execute("UPDATE ml_jobs SET lease_until=clock_timestamp()-interval '1 second'")
   assert await publish(pool,ident,'node',1,1,'RUNNING',{'reason':'','progress':{'input_sha256':'c'*64}},policy) is None
   await pool.execute("UPDATE ml_jobs SET lease_until=clock_timestamp()+interval '120 seconds'")
   result={k:a['domain'][k] for k in ('strategy_id','strategy_version','fingerprint','instrument','requirements','activity_basis','history_provenance')}
   result.update(output={'count':3},input_sha256='c'*64,trading='NO-GO',physical_g1='NOT_AUTHORIZED')
   accepted=await publish(pool,ident,'node',1,2,'COMPLETED',result,policy)
   assert accepted['accepted'] and await publish(pool,ident,'node',1,2,'COMPLETED',result,policy)==accepted
   with pytest.raises(ValueError):await publish(pool,ident,'node',1,2,'COMPLETED',{**result,'output':{'count':4}},policy)
   assert await enqueue(pool,a,policy)==ident
   assert await pool.fetchval('SELECT count(*) FROM ml_jobs')==1
   assert await pool.fetchval('SELECT status FROM ml_jobs')=='done'
   # Real production cleanup must retain the terminal semantic tombstone while
   # preserving ordinary train history retention. These are private fixture rows.
   from grid.maintenance import cleanup_control_metadata
   for name in ('markov_transition_edges','strategy_comparison_results','historical_experiment_runs'):
    await admin.execute(f'CREATE TABLE "{schema}".{name}(dataset_id uuid)')
   await admin.execute(f'CREATE TABLE "{schema}".retention_runs(finished_at timestamptz)')
   old_train=uuid.uuid4()
   await pool.execute("INSERT INTO ml_jobs(id,job_type,payload,status,finished_at) VALUES($1,'train','{}'::jsonb,'done',clock_timestamp()-interval '31 days')",old_train)
   await pool.execute("UPDATE ml_jobs SET finished_at=clock_timestamp()-interval '31 days' WHERE id=$1",uuid.UUID(ident))
   await cleanup_control_metadata(pool)
   assert await pool.fetchval('SELECT id FROM ml_jobs WHERE id=$1',old_train) is None
   assert await enqueue(pool,a,policy)==ident
   assert await pool.fetchval('SELECT status FROM ml_jobs WHERE id=$1',uuid.UUID(ident))=='done'
   assert await pool.fetchval('SELECT count(*) FROM ml_jobs')==1
   await pool.execute("UPDATE ml_jobs SET lease_until=clock_timestamp()-interval '1 second'")
   assert await publish(pool,ident,'node',1,2,'COMPLETED',result,policy)==accepted
   # Expired/current generation cannot publish a new event, even without a rival.
   await pool.execute("UPDATE ml_jobs SET status='running',lease_until=clock_timestamp()-interval '1 second'")
   assert await publish(pool,ident,'node',1,3,'RUNNING',{},policy) is None
  finally:
   try:
    if pool:await pool.close()
    if created:await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    if public_before is not None:assert await _public_objects(admin)==public_before,'public object inventory changed'
   finally:await admin.close()
 asyncio.run(scenario())


def test_real_yield_releases_capacity_restores_checkpoint_and_refunds_slice_attempt():
 async def scenario():
  from grid.ml_dispatcher import MLDispatcher
  dsn=_disposable_dsn(os.environ);schema=_private_schema('data_first_yield_'+uuid.uuid4().hex)
  admin=await asyncpg.connect(dsn,server_settings={'search_path':'pg_catalog'});pool=None;created=False
  public_before=None
  try:
   public_before=await _public_objects(admin)
   await admin.execute(f'CREATE SCHEMA "{schema}"');created=True
   await admin.execute(f'''CREATE TABLE "{schema}".ml_jobs(id uuid PRIMARY KEY,job_type text NOT NULL,payload jsonb NOT NULL,dedupe_key text,status text NOT NULL DEFAULT 'queued',priority integer NOT NULL DEFAULT 1,created_at timestamptz DEFAULT clock_timestamp(),lease_owner text,lease_until timestamptz,started_at timestamptz,finished_at timestamptz,attempts integer DEFAULT 0,max_attempts integer DEFAULT 3,not_before timestamptz,error text,lease_generation bigint DEFAULT 0)''')
   await admin.execute(f'''CREATE TABLE "{schema}".ml_resource_reservations(job_id uuid PRIMARY KEY,node_id text,cpu double precision,ram_gb double precision,scratch_gb double precision,gpu boolean,expires_at timestamptz)''')
   async def setup(c):
    await c.execute(f'SET search_path TO "{schema}"')
    assert await c.fetchval('SELECT current_schema()')==schema
   pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,setup=setup)
   for _ in range(3):
    async with pool.acquire() as connection:assert await connection.fetchval('SELECT current_schema()')==schema
   from grid.migrations import MIGRATIONS
   for sql in next(row[2] for row in MIGRATIONS if row[0]==48):await pool.execute(sql)
   a=request();policy={'a'*40:['b'*64]};ident=await enqueue(pool,a,policy)
   other=copy.deepcopy(a);other['domain']['end_ms']=240000;other_id=await enqueue(pool,other,policy)
   runtime={'data_first_runtime':{'protocol':SCHEMA,'source_commit':'a'*40}}
   async def nodes():return {'node':dict(cpu_pct=0,cpu_count=8,ram_available=8*1024**3,disk_free=100*1024**3,pressure_state='NORMAL',**runtime)}
   dispatcher=MLDispatcher(pool,nodes,data_first_policy=policy)
   async def publish(generation,sequence,state,checkpoint):return await server_publish(pool,ident,'node',generation,sequence,state,checkpoint,policy,request_pin=request_sha(a))
   for generation in (1,2):
    placed=await dispatcher(2 if generation==1 else 1)
    assert [r['job_id'] for r in placed]==[ident] # same instrument cannot have two active owners
    assert await pool.fetchval('SELECT status FROM ml_jobs WHERE id=$1',uuid.UUID(other_id))=='queued'
    job=await claim_data_first(pool,'node',policy,runtime)
    assert job['lease_generation']==generation and job['attempts']==1
    if generation==2:assert job['domain_state']['sequence']==2 and job['domain_state']['checkpoint']['progress']=={'last_page':120000}
    seq=2*generation-1
    assert (await publish(generation,seq,'SYNCING',{'reason':'','progress':{'last_page':120000//generation}}))['accepted']
    yielded=dict(state='PARTIAL' if generation==1 else 'READY',reason='REQUIRED_HISTORY_INCOMPLETE_OR_CANCELLED' if generation==1 else 'RESOURCE_ADMISSION_BLOCKED',progress={'last_page':120000//generation})
    assert (await publish(generation,seq+1,'YIELDED',yielded))['accepted']
    row=await pool.fetchrow('SELECT status,lease_owner,lease_until,attempts,domain_state FROM ml_jobs WHERE id=$1',uuid.UUID(ident))
    assert row['status']=='queued' and row['lease_owner'] is None and row['lease_until'] is None and row['attempts']==0
    assert await pool.fetchval('SELECT count(*) FROM ml_resource_reservations')==0
    assert await publish(generation,seq+1,'YIELDED',yielded) is None
   assert [r['job_id'] for r in await dispatcher(1)]==[ident]
   job=await claim_data_first(pool,'node',policy,runtime);assert job['lease_generation']==3 and job['attempts']==1
   assert (await publish(3,5,'RUNNING',{'reason':'','progress':{'input_sha256':'c'*64}}))['accepted']
   with pytest.raises(ValueError):await publish(3,6,'YIELDED',dict(state='PARTIAL',reason='CANCELLED',progress={}))
   with pytest.raises(ValueError):await publish(3,6,'READY',{'reason':'','progress':{}})
   result={k:a['domain'][k] for k in ('strategy_id','strategy_version','fingerprint','instrument','requirements','activity_basis','history_provenance')}
   result.update(output={'count':3},input_sha256='c'*64,trading='NO-GO',physical_g1='NOT_AUTHORIZED')
   assert (await publish(3,6,'COMPLETED',result))['accepted']
   assert await pool.fetchval('SELECT attempts FROM ml_jobs WHERE id=$1',uuid.UUID(ident))==1
   assert await pool.fetchval('SELECT count(*) FROM ml_resource_reservations')==0
  finally:
   try:
    if pool:await pool.close()
    if created:await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    if public_before is not None:assert await _public_objects(admin)==public_before,'public object inventory changed'
   finally:await admin.close()
 asyncio.run(scenario())
