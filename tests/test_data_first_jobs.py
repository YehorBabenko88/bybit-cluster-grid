import copy
import pytest
from grid.data_first_jobs import validate_request, semantic_id, request_sha, admitted

def request():
 return dict(schema='grid.stratt-data-first.v1',source_commit='a'*40,domain=dict(instrument=dict(category='linear',symbol='ALPHAUSDT',status='Trading',launchTime='0',deliveryTime=None,fundingInterval=None,contractType=None,marketRegion=None,symbolId=None,baseCoin=None,quoteCoin=None),strategy_id='count',strategy_version='1',fingerprint='b'*64,start_ms=0,end_ms=180000,requirements=[dict(symbol='ALPHAUSDT',dataset='candles',timeframe='1m',start_ms=0,end_ms=120000,min_observations=1,required=True)],blockers=[],history_provenance=None,history_fingerprint=None,activity_basis='LAUNCH_DELIVERY_BOUNDS_ONLY'),resources=dict(cpu=1.,ram_gb=1.,scratch_gb=1.,input_gb=0.,gpu=False,data_locality=None))

def test_resource_revision_keeps_job_identity_but_changes_bound_request():
 a=request();b=copy.deepcopy(a);b['resources']['cpu']=2.
 assert semantic_id(a)==semantic_id(b)
 assert request_sha(a)!=request_sha(b)
 assert validate_request(a)==a

def test_source_policy_is_required_and_request_cannot_grant_it():
 a=request()
 assert not admitted(a,None)
 assert not admitted(a,{})
 assert admitted(a,{'a'*40:['b'*64]})
 a['source_admitted']=True
 with pytest.raises(ValueError):validate_request(a)

def test_closed_domain_ranges_estimates_and_secrets_reject():
 for mutate in (lambda x:x.update(password='secret'),lambda x:x['domain'].update(end_ms=0),lambda x:x['resources'].update(cpu=float('nan')),lambda x:x['domain']['instrument'].update(category='unknown'),lambda x:x['domain'].update(blockers=['MISSING_HISTORY'])):
  a=request();mutate(a)
  with pytest.raises(ValueError):validate_request(a)


def test_typed_claim_consumes_only_explicit_train_or_data_first_kind():
 import asyncio
 from grid.ml_worker_protocol import accept_assigned_job
 class Conn:
  def transaction(self):return self
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def fetchrow(self,query,*args):
   if query.lstrip().startswith('SELECT'):
    assert 'job_type=ANY' in query
    assert args[1]==['train']
    return None
 class Pool:
  def acquire(self):return Conn()
 assert asyncio.run(accept_assigned_job(Pool(),'node')) is None


def test_missing_process_launcher_never_claims_a_job():
 import asyncio
 from grid.data_first_agent_worker import run_once
 class Client:
  async def claim(self):raise AssertionError('unadmitted process must not claim')
 assert asyncio.run(run_once(Client()))=={'state':'BLOCKED_PROCESS_LAUNCHER_UNAVAILABLE','claimed':False}

def test_capability_never_substitutes_for_server_source_policy():
 from grid.data_first_jobs import capable,SCHEMA
 a=request();node={'data_first_runtime':{'protocol':SCHEMA,'source_commit':'a'*40}}
 assert not capable(node,a,None)
 assert not capable({},a,{'a'*40:['b'*64]})
 assert capable(node,a,{'a'*40:['b'*64]})


@pytest.mark.parametrize('with_policy,with_capability,busy,want',[(False,True,False,0),(True,False,False,0),(True,True,True,0),(True,True,False,1)])
def test_real_dispatcher_routes_only_admitted_domain_capacity(with_policy,with_capability,busy,want):
 import asyncio,uuid
 from grid.ml_dispatcher import MLDispatcher
 from grid.data_first_jobs import SCHEMA,KIND
 ident=uuid.uuid4();req=request()
 class DB:
  def __init__(self):self.assigned=False;self.reservations=0
  def acquire(self):return self
  def transaction(self):return self
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def fetch(self,sql,*args):
   if 'FROM ml_resource_reservations' in sql:return []
   if 'FROM ml_jobs' in sql:return [] if self.assigned else [dict(id=ident,job_type=KIND,payload=req)]
   raise AssertionError(sql)
  async def fetchval(self,sql,*args):
   if 'count(*)' in sql:return 0
   if 'SELECT EXISTS' in sql:return busy
   raise AssertionError(sql)
  async def execute(self,sql,*args):
   if "UPDATE ml_jobs SET status='assigned'" in sql:self.assigned=True
   if 'INSERT INTO ml_resource_reservations' in sql:self.reservations+=1
   return 'UPDATE 1'
 db=DB()
 async def nodes():
  node=dict(cpu_pct=0,cpu_count=8,ram_available=8*1024**3,disk_free=100*1024**3,pressure_state='NORMAL')
  if with_capability:node['data_first_runtime']={'protocol':SCHEMA,'source_commit':'a'*40}
  return {'node':node}
 out=asyncio.run(MLDispatcher(db,nodes,data_first_policy={'a'*40:['b'*64]} if with_policy else None)(1))
 assert len(out)==want and db.reservations==want and db.assigned==bool(want)


def test_expired_running_same_sequence_is_not_a_fresh_ack():
 import asyncio,hashlib,json,uuid
 from grid.data_first_jobs import publish,request_sha,KIND
 value=request();ident=uuid.uuid4();body=dict(sequence=1,state='RUNNING',checkpoint={'reason':'','progress':{'input_sha256':'c'*64}})
 digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 class DB:
  def acquire(self):return self
  def transaction(self):return self
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def fetchrow(self,*args):return dict(id=ident,job_type=KIND,lease_owner='node',lease_generation=1,payload=value,status='running',domain_state={**body,'sha256':digest})
  async def fetchval(self,*args):return False
 result=asyncio.run(publish(DB(),str(ident),'node',1,1,'RUNNING',body['checkpoint'],{'a'*40:['b'*64]},request_pin=request_sha(value)))
 assert result is None


def test_completed_identical_receipt_remains_replayable_after_expiry():
 import asyncio,hashlib,json,uuid
 from grid.data_first_jobs import publish,request_sha,KIND
 value=request();ident=uuid.uuid4();body=dict(sequence=2,state='COMPLETED',checkpoint={'accepted_result':'historic'})
 digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 class DB:
  def acquire(self):return self
  def transaction(self):return self
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def fetchrow(self,*args):return dict(id=ident,job_type=KIND,lease_owner='node',lease_generation=1,payload=value,status='done',domain_state={**body,'sha256':digest})
  async def fetchval(self,*args):return False
 result=asyncio.run(publish(DB(),str(ident),'node',1,2,'COMPLETED',body['checkpoint'],{'a'*40:['b'*64]},request_pin=request_sha(value)))
 assert result['accepted'] is True and result['sha256']==digest


def test_running_attempt_cannot_hide_execution_by_returning_to_ready():
 import asyncio,hashlib,json,uuid
 from grid.data_first_jobs import publish,request_sha,KIND
 value=request();ident=uuid.uuid4();body=dict(sequence=1,state='RUNNING',checkpoint={'reason':'','progress':{'input_sha256':'c'*64}})
 digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 class DB:
  def acquire(self):return self
  def transaction(self):return self
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def fetchrow(self,*args):return dict(id=ident,job_type=KIND,lease_owner='node',lease_generation=1,payload=value,status='running',domain_state={**body,'sha256':digest})
  async def fetchval(self,query,*args):
   assert query.startswith('SELECT lease_until') # reject before any mutation
   return True
 with pytest.raises(ValueError):asyncio.run(publish(DB(),str(ident),'node',1,2,'READY',{'reason':'','progress':{}},{'a'*40:['b'*64]},request_pin=request_sha(value)))


class _DataFirstOnTrainRoute:
 """SQL-boundary fake, NOT PostgreSQL execution evidence."""
 def __init__(self):self.writes=[];self.reads=[]
 def acquire(self):return self
 def transaction(self):return self
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 async def fetchrow(self,query,*args):
  import uuid
  self.reads.append(query)
  if 'FROM ml_jobs' in query:
   if "job_type='train'" in query or "job_type<>'stratt_data_first_v1'" in query:return None
   return dict(payload={'dataset_id':str(uuid.UUID(int=2))},attempts=1,max_attempts=3,id=uuid.UUID(int=1))
  if 'dataset_snapshots' in query:return dict(id='dataset',dataset_hash='hash',feature_version='v1',sample_count=0)
  if 'ml_artifacts' in query:return {'id':'artifact'}
  raise AssertionError(query)
 async def fetch(self,*args):return []
 async def fetchval(self,query,*args):
  self.reads.append(query)
  return None if "job_type='train'" in query else True
 async def execute(self,query,*args):
  if "job_type<>'stratt_data_first_v1'" in query:return 'UPDATE 0'
  self.writes.append(query);return 'UPDATE 1'

@pytest.mark.parametrize('route',['dataset','register','artifact','finalize'])
def test_running_data_first_cannot_use_training_publication_routes(route):
 import asyncio,hashlib,uuid
 from grid import ml_transport as transport
 pool=_DataFirstOnTrainRoute();puts=[]
 class Store:
  def put_bytes(self,data):puts.append(data);return dict(id=uuid.uuid4(),storage_uri='artifact://fixture',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 async def run():
  args=(pool,uuid.UUID(int=1),'node',7)
  if route=='dataset':return await transport.dataset_page(*args)
  if route=='register':return await transport.register_saved_artifact(*args,dict(id=uuid.uuid4(),storage_uri='artifact://fixture',bytes=1,sha256='a'*64))
  if route=='artifact':return await transport.publish_artifact(pool,Store(),*args[1:],b'model',hashlib.sha256(b'model').hexdigest())
  return await transport.finalize_model(*args,uuid.UUID(int=3))
 assert asyncio.run(run()) in (None,False)
 assert puts==[] and pool.writes==[]
 assert len(pool.reads)==1 # no dataset/model reads after rejecting the kind

def test_running_data_first_cannot_finish_or_fail_through_generic_ml_helpers():
 import asyncio,uuid
 from grid.ml_worker_protocol import complete_running_job,fail_running_job
 async def run():
  pool=_DataFirstOnTrainRoute()
  assert await complete_running_job(pool,uuid.UUID(int=1),'node',7) is False
  assert await fail_running_job(pool,uuid.UUID(int=1),'node',7,ValueError('fixture'))=='stale'
  assert pool.writes==[]
 asyncio.run(run())

def test_streamed_model_upload_checks_train_kind_before_creating_any_file(monkeypatch):
 import asyncio
 from fastapi import HTTPException
 from grid import coordinator as control
 from types import SimpleNamespace
 pool=_DataFirstOnTrainRoute();monkeypatch.setattr(control,'db',SimpleNamespace(pool=pool))
 async def auth(*args):pass
 monkeypatch.setattr(control,'node_auth',auth)
 def forbidden(*args):raise AssertionError('DATA_FIRST_MODEL_FILE_WRITE')
 monkeypatch.setattr(control,'LocalArtifactStore',forbidden)
 class Request:
  headers={}
  async def stream(self):raise AssertionError('DATA_FIRST_STREAM_CONSUMED');yield b''
 with pytest.raises(HTTPException) as caught:asyncio.run(control.upload_ml_artifact('00000000-0000-0000-0000-000000000001',Request(),'node',7,'a'*64))
 assert caught.value.status_code==409 and pool.writes==[]


def test_model_finalize_rechecks_train_kind_in_locked_transaction():
 import asyncio,uuid
 from grid.ml_transport import finalize_model
 class ChangedAfterRead(_DataFirstOnTrainRoute):
  seen=0
  async def fetchrow(self,query,*args):
   if 'FROM ml_jobs' in query:
    self.seen+=1
    if self.seen==1:return {'payload':{'dataset_id':uuid.UUID(int=2)}}
   return await super().fetchrow(query,*args)
 pool=ChangedAfterRead()
 assert asyncio.run(finalize_model(pool,uuid.UUID(int=1),'node',7,uuid.UUID(int=3))) is False
 assert pool.seen==2 and pool.writes==[]

def test_data_first_renewal_remains_shared_while_terminal_routes_are_closed():
 import asyncio,uuid
 from grid.ml_transport import renew
 pool=_DataFirstOnTrainRoute()
 assert asyncio.run(renew(pool,uuid.UUID(int=1),'node',7)) is True
 assert len(pool.writes)==2
 assert all('UPDATE' in sql for sql in pool.writes)


def test_metadata_cleanup_preserves_domain_dedupe_tombstone_but_expires_train_history():
 import asyncio
 from grid.maintenance import cleanup_control_metadata
 class Pool:
  def __init__(self):self.terminal={'domain':'stratt_data_first_v1','train':'train'}
  async def execute(self,query,*args):
   if 'DELETE FROM ml_jobs' in query:
    removed=[key for key,kind in self.terminal.items() if not ("j.job_type<>'stratt_data_first_v1'" in query and kind=='stratt_data_first_v1')]
    for key in removed:del self.terminal[key]
    return 'DELETE '+str(len(removed))
   return 'UPDATE 0'
 pool=Pool();result=asyncio.run(cleanup_control_metadata(pool))
 assert pool.terminal=={'domain':'stratt_data_first_v1'} and result['jobs']=='DELETE 1'


def test_private_pg_fixture_refuses_ambient_dsn_outside_fixed_hosted_job(monkeypatch):
 import asyncpg
 from tests.test_data_first_jobs_postgres import _disposable_dsn,_private_schema
 def forbidden(*a,**k):raise AssertionError('UNIT_GUARD_MUST_NOT_CONNECT')
 monkeypatch.setattr(asyncpg,'connect',forbidden);monkeypatch.setattr(asyncpg,'create_pool',forbidden)
 good=dict(HISTORY_DISPOSABLE_DSN='postgresql://grid:grid@127.0.0.1:5432/grid',MISSION3_TEST_DATABASE_URL='postgresql://grid:grid@127.0.0.1:5432/grid',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid',GITHUB_JOB='linux-postgres18')
 assert _disposable_dsn(good)==good['HISTORY_DISPOSABLE_DSN']
 assert _private_schema('data_first_test_'+'a'*32)=='data_first_test_'+'a'*32
 for schema in ('public','data_first_test_short','data_first_test_'+'a'*32+';DROP SCHEMA public'):
  with pytest.raises(ValueError):_private_schema(schema)
 for changes in ({'GITHUB_ACTIONS':'false'},{'RUNNER_ENVIRONMENT':'self-hosted'},{'HISTORY_DISPOSABLE_DSN':'postgresql://office/db'},{'GITHUB_JOB':'unreviewed'},{'MISSION3_TEST_DATABASE_URL':'postgresql://other/db'},{'GITHUB_REPOSITORY':'foreign/repo'}):
  with pytest.raises(ValueError):_disposable_dsn({**good,**changes})
