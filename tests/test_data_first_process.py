"""Process/IPC primitives; fake admission does not qualify deployment."""
import asyncio,io,json,hashlib
import pytest
from grid.data_first_process import DataFirstProcess,ProcessBlocked,encode_frame,decode_frame

def test_ipc_is_closed_bounded_nonce_bound_and_canonical():
 raw=encode_frame('a'*64,1,'RENEW',{})
 assert decode_frame(raw,'a'*64,1)==('RENEW',{})
 for bad in (raw.replace(b'a',b'b',1),raw[:-1],b'x'*1048577,raw.replace(b'RENEW',b'UNKNOWN'),raw.replace(b'{}',b'{"extra":1}')):
  with pytest.raises(ProcessBlocked):decode_frame(bad,'a'*64,1)

def test_missing_or_revoked_admission_blocks_before_claim():
 from grid.data_first_agent_worker import run_once
 class Client:
  async def claim(self):raise AssertionError('claimed without current proof')
 for admission in (None,{},object()):
  with pytest.raises(ProcessBlocked):asyncio.run(run_once(Client(),process_launcher=DataFirstProcess(admission)))


def admitted_fixture(tmp_path):
 import copy
 source=tmp_path/'source';(source/'strattester/engine').mkdir(parents=True)
 worker=source/'strattester/engine/grid_data_first_worker.py';worker.write_bytes(b'# source-only fixture\n')
 python=tmp_path/'python.exe';python.write_bytes(b'inert fixture binary')
 bootstrap=tmp_path/'owned_python.py';bootstrap.write_bytes(b'# inert pinned bootstrap\n')
 workspace=tmp_path/'work';workspace.mkdir()
 pin=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 spec=dict(python=str(python.resolve()),python_sha256=pin(python),bootstrap=str(bootstrap.resolve()),bootstrap_sha256=pin(bootstrap),source_root=str(source.resolve()),source_commit='a'*40,worker_sha256=pin(worker),dependency_roots=[],workspace_root=str(workspace.resolve()),system_root=None,module_version='1.0.0',release_id='fixture',network_scope='PUBLIC_GET_ONLY_RESEARCH',timeout_seconds=2,ram_limit_mb=64)
 class Admission:
  live=True
  def require_current(self):return self.live
  def process_spec(self):return copy.deepcopy(spec)
 return Admission(),workspace

def fake_process(monkeypatch,mode):
 import types
 import grid.data_first_process as module
 events=[];created=asyncio.Event()
 class Reader:
  def __init__(self):self.queue=asyncio.Queue()
  async def readline(self):return await self.queue.get()
  async def read(self,n):
   if mode=='secret':return b'SECRET_CREDENTIAL'
   await process.exited.wait();return b''
 class Writer:
  def write(self,raw):
   value=json.loads(raw);events.append(('write',value['op']))
   if value['op']=='INIT':
    nonce=value['nonce'];self.nonce=nonce
    if mode=='eof':process.stdout.queue.put_nowait(b'')
    elif mode=='malformed':process.stdout.queue.put_nowait(b'SECRET_CREDENTIAL\n')
    elif mode=='oversize':process.stdout.queue.put_nowait(b'x'*1048577)
    elif mode=='nonce':process.stdout.queue.put_nowait(encode_frame('b'*64,1,'RENEW',{}))
    elif mode not in ('wait','secret'):process.stdout.queue.put_nowait(encode_frame(nonce,1,'RENEW',{}))
   elif value['op']=='ACK' and mode=='success':
    if value['body']['op']=='RENEW':process.stdout.queue.put_nowait(encode_frame(self.nonce,2,'CHECKPOINT',dict(sequence=1,state='YIELDED',checkpoint={'state':'PARTIAL','reason':'CANCELLED','progress':{}})))
    else:
     ack=value['body']['value'];process.stdout.queue.put_nowait(encode_frame(self.nonce,3,'DONE',dict(sequence=1,state=ack['state'],sha256=ack['sha256'])));process.returncode=0;process.exited.set()
  async def drain(self):await asyncio.sleep(0)
 class Process:
  pid=456789;returncode=None
  def __init__(self):self.exited=asyncio.Event();self.stdin=Writer();self.stdout=Reader();self.stderr=Reader();self.descendant_alive=True
  async def wait(self):await self.exited.wait();events.append(('joined',self.pid));return self.returncode
  def kill(self):self.returncode=-9;self.descendant_alive=False;self.exited.set();events.append(('kill',self.pid))
 process=Process()
 async def spawn(*args,**kwargs):
  events.append(('spawn',args,kwargs));created.set();return process
 class Info:
  def create_time(self):return 123.
  def memory_info(self):return types.SimpleNamespace(rss=1024)
  def children(self,recursive=True):return []
 class Job:
  def __init__(self,pid,resume_primary_thread=False):events.append(('job_assigned',pid,resume_primary_thread))
  def terminate_and_wait(self,timeout):
   events.append(('job_empty_proof',process.pid));self.close();return True
  def close(self):events.append(('job_closed',process.pid));process.descendant_alive=False
 async def terminate(proc,grace_seconds):
  events.append(('terminate',proc.pid));proc.kill();await proc.wait()
 # Model the Windows branch only; no real subprocess/kernel calls use this backend.
 monkeypatch.setattr(module,'os',types.SimpleNamespace(name='nt',fstat=module.os.fstat,walk=module.os.walk))
 monkeypatch.setattr(module.asyncio,'create_subprocess_exec',spawn);monkeypatch.setattr(module.psutil,'Process',lambda pid:Info());monkeypatch.setattr(module,'terminate_process_tree',terminate)
 import grid.ml_windows_job
 monkeypatch.setattr(grid.ml_windows_job,'WindowsJob',Job)
 return process,events,created

class Client:
 def __init__(self,valid=True):self.valid=valid;self.checkpoints=[]
 async def renew(self,job):return {'ok':True} if self.valid else None
 async def checkpoint(self,job,sequence,state,checkpoint):
  from grid.data_first_jobs import request_sha
  body=dict(sequence=sequence,state=state,checkpoint=checkpoint);self.checkpoints.append(body)
  return dict(accepted=True,state=state,sha256=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest(),request_sha256=request_sha(job['payload']))

def test_fixed_launch_uses_only_admitted_paths_environment_and_server_receipt(tmp_path,monkeypatch):
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,'success')
  monkeypatch.setenv('SECRET_CREDENTIAL','must-not-inherit');job=dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1)
  result=await DataFirstProcess(admission).run_supervised(job,Client())
  assert result['state']=='YIELDED' and result['deployment']=='NOT_QUALIFIED'
  spawn=next(event for event in events if event[0]=='spawn');argv,options=spawn[1:]
  assert argv[-2:]==('--module','strattester.engine.grid_data_first_worker') and argv[1:4]==('-I','-S','-B')
  assert 'SECRET_CREDENTIAL' not in options['env'] and 'PYTHONPATH' not in options['env']
  assert options['env']['UNIFIED_ORDER_MODE']=='PAPER_ONLY'
  assert not list(workspace.iterdir()) and not proc.descendant_alive
  assert any(event[0]=='joined' for event in events)
 asyncio.run(run())

@pytest.mark.parametrize('mode,code',[('eof','PROCESS_PIPE_EOF'),('malformed','PROCESS_PROTOCOL_REJECTED'),('oversize','PROCESS_PROTOCOL_REJECTED'),('nonce','PROCESS_PROTOCOL_REJECTED'),('secret','PROCESS_OUTPUT_REJECTED'),('lease','PROCESS_LEASE_FENCED')])
def test_bad_ipc_or_lost_lease_kills_and_joins_without_raw_diagnostics(tmp_path,monkeypatch,mode,code):
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,mode)
  with pytest.raises(ProcessBlocked) as caught:await DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client(valid=mode!='lease'))
  assert str(caught.value)==code and 'SECRET' not in str(caught.value)
  assert not proc.descendant_alive and any(event[0]=='joined' for event in events) and not list(workspace.iterdir())
 asyncio.run(run())

def test_cancel_waits_for_owned_tree_cleanup_before_returning(tmp_path,monkeypatch):
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,created=fake_process(monkeypatch,'wait')
  task=asyncio.create_task(DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client()))
  await created.wait();await asyncio.sleep(0);task.cancel()
  with pytest.raises(asyncio.CancelledError):await task
  assert not proc.descendant_alive and any(event[0]=='joined' for event in events) and not list(workspace.iterdir())
 asyncio.run(run())

def test_revoked_valid_admission_blocks_before_claim(tmp_path,monkeypatch):
 import types
 import grid.data_first_process as module
 monkeypatch.setattr(module,"os",types.SimpleNamespace(name="nt",fstat=module.os.fstat))
 from grid.data_first_agent_worker import run_once
 admission,_=admitted_fixture(tmp_path);launcher=DataFirstProcess(admission);assert launcher.require_admitted() is True;admission.live=False
 class NoClaim:
  async def claim(self):raise AssertionError('claim after revocation')
 with pytest.raises(ProcessBlocked):asyncio.run(run_once(NoClaim(),process_launcher=launcher))


def test_job_close_exit_race_joins_owned_handle_without_pid_termination(tmp_path,monkeypatch):
 import grid.data_first_process as module
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,'eof');ordinary=module.psutil.Process
  def info(pid):
   if any(event[0]=='job_closed' for event in events):
    asyncio.get_running_loop().call_soon(proc.kill)
    raise module.psutil.NoSuchProcess(pid)
   return ordinary(pid)
  monkeypatch.setattr(module.psutil,'Process',info)
  with pytest.raises(ProcessBlocked) as caught:await DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client())
  assert str(caught.value)=='PROCESS_PIPE_EOF'
  assert any(event[0]=='joined' for event in events) and not any(event[0]=='terminate' for event in events)
 asyncio.run(run())


def test_cleanup_failure_latches_before_any_retry_claim(tmp_path,monkeypatch):
 import grid.data_first_process as module
 from grid.data_first_agent_worker import run_once
 from tests.test_data_first_jobs import request
 async def run():
  admission,_=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,'eof')
  async def broken(*args,**kwargs):raise RuntimeError('SECRET_CREDENTIAL')
  monkeypatch.setattr(module,'terminate_process_tree',broken);launcher=DataFirstProcess(admission)
  with pytest.raises(ProcessBlocked,match='^PROCESS_CLEANUP_UNAVAILABLE$'):await launcher.run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client())
  class NoRetry:
   async def claim(self):raise AssertionError('retry before owned child joined')
  with pytest.raises(ProcessBlocked,match='^PROCESS_CLEANUP_UNAVAILABLE$'):await run_once(NoRetry(),process_launcher=launcher)
  proc.kill() # fake-process cleanup only
 asyncio.run(run())

def test_repeated_cancel_cannot_abandon_cleanup_task(tmp_path,monkeypatch):
 import grid.data_first_process as module
 from tests.test_data_first_jobs import request
 async def run():
  admission,_=admitted_fixture(tmp_path);proc,events,created=fake_process(monkeypatch,'wait');entered=asyncio.Event();release=asyncio.Event()
  async def slow_cleanup(proc,grace_seconds):
   entered.set();await release.wait();proc.kill();await proc.wait()
  monkeypatch.setattr(module,'terminate_process_tree',slow_cleanup)
  task=asyncio.create_task(DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client()))
  await created.wait();await asyncio.sleep(0);task.cancel();await entered.wait();task.cancel();await asyncio.sleep(0)
  assert not task.done();release.set()
  with pytest.raises(asyncio.CancelledError):await task
  assert not proc.descendant_alive and any(event[0]=='joined' for event in events)
 asyncio.run(run())


def test_numeric_true_is_not_a_valid_lease_acknowledgement(tmp_path,monkeypatch):
 from tests.test_data_first_jobs import request
 async def run():
  admission,_=admitted_fixture(tmp_path);fake_process(monkeypatch,'lease')
  class Numeric(Client):
   async def renew(self,job):return {'ok':1}
  with pytest.raises(ProcessBlocked,match='^PROCESS_LEASE_FENCED$'):await DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Numeric())
 asyncio.run(run())


@pytest.mark.skipif(__import__('os').name!='nt',reason='actual owned Windows Job process-tree integration')
def test_actual_owned_windows_child_tree_is_joined_on_cancellation(tmp_path,monkeypatch):
 import os,sys,time
 from pathlib import Path
 import grid.data_first_process as module
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);base=admission.process_spec;spec=base();source=Path(spec['source_root'])
  worker=source/'strattester/engine/grid_data_first_worker.py'
  worker.write_text("import json,os,pathlib,subprocess,sys,time\nmsg=json.loads(sys.stdin.buffer.readline())\nchild=subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time;time.sleep(60)'])\npathlib.Path('owned-child.json').write_text(json.dumps({'pid':child.pid,'parent':os.getpid()}))\ntime.sleep(60)\n")
  bootstrap=Path(spec['bootstrap']);bootstrap.write_text("import pathlib,runpy,sys\nroot=pathlib.Path(sys.argv[sys.argv.index('--source-root')+1])\nrunpy.run_path(str(root/'strattester/engine/grid_data_first_worker.py'),run_name='__main__')\n")
  python=Path(sys.executable).resolve();spec.update(python=str(python),python_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),bootstrap_sha256=hashlib.sha256(bootstrap.read_bytes()).hexdigest(),worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),system_root=str(Path(os.environ['SystemRoot']).resolve()),timeout_seconds=10,ram_limit_mb=256)
  admission.process_spec=lambda:dict(spec)
  actual=module.asyncio.create_subprocess_exec;spawned=[]
  async def capture(*args,**kwargs):
   proc=await actual(*args,**kwargs);spawned.append(proc);return proc
  monkeypatch.setattr(module.asyncio,'create_subprocess_exec',capture)
  task=asyncio.create_task(DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client()))
  owned=None;birth=None
  try:
   deadline=asyncio.get_running_loop().time()+5
   while asyncio.get_running_loop().time()<deadline:
    markers=list(workspace.glob('data-first-*/owned-child.json'))
    if markers:
     try:owned=json.loads(markers[0].read_text())['pid'];break
     except (OSError,ValueError):pass
    if task.done():await task
    await asyncio.sleep(.02)
   assert owned is not None
   descendant=module.psutil.Process(owned);birth=descendant.create_time()
   assert owned in [p.pid for p in module.psutil.Process(spawned[0].pid).children(recursive=True)]
   task.cancel()
   with pytest.raises(asyncio.CancelledError):await task
   assert spawned[0].returncode is not None
   try:assert module.psutil.Process(owned).create_time()!=birth or not module.psutil.Process(owned).is_running()
   except module.psutil.NoSuchProcess:pass
   assert not list(workspace.iterdir())
  finally:
   if not task.done():task.cancel()
   await asyncio.gather(task,return_exceptions=True)
   if owned is not None:
    try:
     process=module.psutil.Process(owned)
     if process.create_time()==birth:process.kill();process.wait(timeout=5)
    except module.psutil.NoSuchProcess:pass
 asyncio.run(run())


def test_revocation_during_pin_admission_is_rechecked_before_claim(tmp_path):
 from grid.data_first_agent_worker import run_once
 admission,_=admitted_fixture(tmp_path);original=admission.process_spec
 def revoked_snapshot():
  value=original();admission.live=False;return value
 admission.process_spec=revoked_snapshot
 class NoClaim:
  async def claim(self):raise AssertionError('claimed after proof changed during pin reads')
 with pytest.raises(ProcessBlocked,match='^PROCESS_ADMISSION_REVOKED$'):asyncio.run(run_once(NoClaim(),process_launcher=DataFirstProcess(admission)))


def test_normal_exit_waits_for_delayed_job_empty_before_workspace_delete(tmp_path,monkeypatch):
 import grid.ml_windows_job
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,'success');base=grid.ml_windows_job.WindowsJob
  class Delayed(base):
   def terminate_and_wait(self,timeout):
    assert list(workspace.iterdir()) # no scratch deletion before empty proof
    for count in (2,1,0):events.append(('active_descendants',count))
    self.close();return True
  monkeypatch.setattr(grid.ml_windows_job,'WindowsJob',Delayed)
  result=await DataFirstProcess(admission).run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client())
  assert result['state']=='YIELDED' and [event[1] for event in events if event[0]=='active_descendants']==[2,1,0]
  assert not list(workspace.iterdir())
 asyncio.run(run())


@pytest.mark.parametrize('failure',['missing','timeout','false'])
def test_unproven_job_empty_retains_scratch_and_denies_retry(tmp_path,monkeypatch,failure):
 import grid.ml_windows_job
 from grid.data_first_agent_worker import run_once
 from tests.test_data_first_jobs import request
 async def run():
  admission,workspace=admitted_fixture(tmp_path);proc,events,_=fake_process(monkeypatch,'success');base=grid.ml_windows_job.WindowsJob
  class Unproven(base):
   def terminate_and_wait(self,timeout):
    if failure=='timeout':raise TimeoutError('SECRET_DETAIL')
    return False
  if failure=='missing':Unproven.terminate_and_wait=None
  monkeypatch.setattr(grid.ml_windows_job,'WindowsJob',Unproven);launcher=DataFirstProcess(admission)
  with pytest.raises(ProcessBlocked,match='^PROCESS_CLEANUP_UNAVAILABLE$'):await launcher.run_supervised(dict(id='fixture',job_type='stratt_data_first_v1',payload=request(),lease_owner='node',lease_generation=1),Client())
  assert list(workspace.iterdir()) and any(event[0]=='joined' for event in events)
  class NoRetry:
   async def claim(self):raise AssertionError('claim without Job-empty proof')
  with pytest.raises(ProcessBlocked,match='^PROCESS_CLEANUP_UNAVAILABLE$'):await run_once(NoRetry(),process_launcher=launcher)
 asyncio.run(run())


def test_non_windows_blocks_before_admission_claim_workspace_or_spawn(tmp_path,monkeypatch):
 import types
 import grid.data_first_process as module
 from grid.data_first_agent_worker import run_once
 admission,workspace=admitted_fixture(tmp_path)
 def forbidden(*args,**kwargs):raise AssertionError('effect before platform admission')
 admission.require_current=forbidden;admission.process_spec=forbidden
 monkeypatch.setattr(module,'os',types.SimpleNamespace(name='posix'))
 monkeypatch.setattr(module.tempfile,'mkdtemp',forbidden)
 monkeypatch.setattr(module.asyncio,'create_subprocess_exec',forbidden)
 class NoClaim:
  async def claim(self):forbidden()
 with pytest.raises(ProcessBlocked,match='^PROCESS_PLATFORM_UNQUALIFIED$'):
  asyncio.run(run_once(NoClaim(),process_launcher=DataFirstProcess(admission)))
 assert not list(workspace.iterdir())
