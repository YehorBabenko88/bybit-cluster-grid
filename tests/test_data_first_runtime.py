import copy,hashlib
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def central_policy_source(monkeypatch):
 # Required explicit cross-repo source dependency; no fake policy or silent skip.
 import os,sys,types
 source=os.environ.get('UNIFIED_SOURCE_ROOT')
 if not source:pytest.fail('UNIFIED_SOURCE_ROOT required for real central policy integration')
 parent=types.ModuleType('unified_system');parent.__path__=[str(Path(source)/'unified_system')]
 monkeypatch.setitem(sys.modules,'unified_system',parent)
 for name in ('data_first_policy','service_bootstrap','data_first_workspace'):
  path=Path(source)/('unified_system/'+name+'.py')
  if not path.is_file():pytest.fail('central policy/workspace source missing: '+name)
  module=types.ModuleType('unified_system.'+name);module.__file__=str(path)
  monkeypatch.setitem(sys.modules,module.__name__,module)
  exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)

def fixture(tmp_path):
 service=tmp_path/'service';service.mkdir();root=service/'code';state=service/'state';state.mkdir();files={}
 def file(name):
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'pinned fixture');files[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size};return p
 python=file('python/python.exe');file('sources/grid/owned.txt');file('sources/unified-system/unified_system/service_entry.py');file('sources/strattester/strattester/engine/grid_data_first_worker.py');(root/'dependencies/site-packages').mkdir(parents=True)
 manifest={'files':files,'sources':{'grid':{'root':'sources/grid','commit':'d'*40},'strattester':{'root':'sources/strattester','commit':'a'*40,'version':'0.1.0'},'unified-system':{'root':'sources/unified-system'}}}
 config={'state_root':str(state),'release_id':'test','programs':{'grid':{'argv':[str(python)],'external_file_pins':{}}}}
 capability=dict(schema='unified.data-first-runtime.v1',source_commit='a'*40,strategy_fingerprints=['b'*64],categories=['linear'],network_scope='BYBIT_PUBLIC_GET_ONLY',workspace_relative='data-first',limits=dict(timeout_seconds=10,ram_limit_mb=128,max_pages=1,max_observations=1000,requests_per_second=2))
 class Grant:
  code_root=root;live=True;profile={'data_first':capability};descriptor={'service_plan':dict(installation_id='install-1',node_id='NODE1',service_name='UnifiedLab_test',service_sid='S-1-5-80-1-2-3-4-5',computer_name='LABHOST',root=str(service),state=str(state))};service_sid='S-1-5-80-1-2-3-4-5';computer_name='LABHOST'
  def require_current(self):return self.live
 grant=Grant()
 return grant,lambda g:(copy.deepcopy(config),copy.deepcopy(manifest)),state

def test_supplier_consumes_readmission_and_fixed_raw_entry(tmp_path,monkeypatch):
 import grid.data_first_runtime as module
 monkeypatch.setattr(module,"windows_root",lambda:str(tmp_path))
 from grid.data_first_runtime import ProtectedDataFirstAdmission
 grant,readmit,state=fixture(tmp_path);admission=ProtectedDataFirstAdmission(grant,readmit)
 assert admission.require_current() is True
 spec=admission.process_spec()
 assert spec['bootstrap'].endswith('service_entry.py') and spec['source_commit']=='a'*40
 assert Path(spec['workspace_root'])==state/'data-first' and Path(spec['workspace_root']).is_dir()
 grant.live=False
 with pytest.raises(Exception):admission.require_current()

@pytest.mark.parametrize('mutation',[lambda g:g.profile.clear(),lambda g:g.profile['data_first'].update(network_scope='ANY'),lambda g:g.profile['data_first'].update(workspace_relative='../foreign'),lambda g:g.profile['data_first'].update(source_commit='c'*40)])
def test_invalid_permission_blocks_before_workspace(tmp_path,mutation):
 from grid.data_first_runtime import ProtectedDataFirstAdmission
 grant,readmit,state=fixture(tmp_path);mutation(grant)
 with pytest.raises(Exception):ProtectedDataFirstAdmission(grant,readmit).process_spec()
 assert not (state/'data-first').exists()

def test_revoked_during_readmission_cannot_create_workspace(tmp_path):
 from grid.data_first_runtime import ProtectedDataFirstAdmission
 grant,readmit,state=fixture(tmp_path)
 def revoke(g):
  result=readmit(g);g.live=False;return result
 with pytest.raises(Exception):ProtectedDataFirstAdmission(grant,revoke).process_spec()
 assert not (state/'data-first').exists()


def test_worker_optional_injection_is_explicit_and_capability_revokes(tmp_path,monkeypatch):
 import grid.worker as module
 class Store:
  def __init__(self,*a,**kw):pass
 for name in ('Storage','MicroEventStorage','LocalControlJournal','ControlSnapshotRing','CommandReceiptStore'):
  monkeypatch.setattr(module,name,Store)
 class Launcher:
  live=True
  def __init__(self,a):self.a=a
  def require_admitted(self):
   if not self.live:raise ValueError('revoked')
   return True
 monkeypatch.setattr('grid.data_first_process.DataFirstProcess',Launcher)
 class Admission:
  def runtime_capability(self):return {'protocol':'grid.stratt-data-first.v1','source_commit':'a'*40}
 assert module.Worker().data_first_capability() is None
 worker=module.Worker(data_first_admission=Admission())
 worker.data_first_task=type('LiveModel',(),{'done':lambda self:False})()
 assert worker.data_first_capability()['source_commit']=='a'*40
 worker.data_first_launcher.live=False
 assert worker.data_first_capability() is None


def test_consumed_worker_loop_uses_existing_transport_and_stops_on_failure(monkeypatch):
 import asyncio
 import grid.worker as module
 class Launcher:
  pass
 worker=object.__new__(module.Worker);worker.ml_stop=asyncio.Event();worker.data_first_launcher=Launcher()
 worker._data_first_can_claim=lambda:True
 calls=[]
 client=object()
 monkeypatch.setattr('grid.ml_transport_client.DataFirstTransportClient',lambda node:client)
 async def run_once(actual,*,process_launcher):
  assert actual is client and process_launcher is worker.data_first_launcher
  calls.append(True);raise ValueError('PRIVATE transport detail')
 monkeypatch.setattr('grid.data_first_agent_worker.run_once',run_once)
 asyncio.run(worker._data_first_loop())
 assert calls==[True]


def test_current_checks_use_live_revision_without_rehashing_capsule_each_monitor(tmp_path):
 from grid.data_first_runtime import ProtectedDataFirstAdmission
 grant,readmit,_=fixture(tmp_path);calls=[]
 def observe(g):calls.append(True);return readmit(g)
 admission=ProtectedDataFirstAdmission(grant,observe)
 for _ in range(4):assert admission.require_current() is True
 admission.runtime_capability()
 assert calls==[True]
 grant.live=False
 with pytest.raises(Exception):admission.require_current()


def test_every_process_spec_repeats_full_readmission_but_monitor_does_not(tmp_path,monkeypatch):
 import grid.data_first_runtime as module
 grant,readmit,_=fixture(tmp_path);calls=[]
 monkeypatch.setattr(module,'windows_root',lambda:str(tmp_path))
 def observe(g):calls.append(True);return readmit(g)
 admission=module.ProtectedDataFirstAdmission(grant,observe)
 admission.process_spec()
 for _ in range(4):admission.require_current()
 assert len(calls)==1
 admission.process_spec()
 assert len(calls)==2

@pytest.mark.parametrize('changed',['source','config'])
def test_second_child_readmission_change_rejects_before_claim_or_spawn(tmp_path,monkeypatch,changed):
 import asyncio,types
 import grid.data_first_runtime as runtime
 import grid.data_first_process as process
 from grid.data_first_agent_worker import run_once
 grant,readmit,state=fixture(tmp_path);calls=[];change=False
 monkeypatch.setattr(runtime,'windows_root',lambda:str(tmp_path))
 # Explicit modeled Windows admission; no native platform qualification.
 monkeypatch.setattr(process,'os',types.SimpleNamespace(name='nt',fstat=process.os.fstat))
 def observed(g):
  calls.append(True);config,manifest=readmit(g)
  if change:
   if changed=='source':manifest['sources']['strattester']['commit']='c'*40
   else:config['release_id']='changed'
  return config,manifest
 admission=runtime.ProtectedDataFirstAdmission(grant,observed)
 admission.process_spec();before=list((state/'data-first').iterdir());change=True
 def forbidden(*a,**kw):raise AssertionError('effect after changed readmission')
 monkeypatch.setattr(process.asyncio,'create_subprocess_exec',forbidden)
 class NoClaim:
  async def claim(self):forbidden()
 with pytest.raises(process.ProcessBlocked,match='^PROCESS_(SOURCE_REJECTED|ADMISSION_REVOKED)$'):asyncio.run(run_once(NoClaim(),process_launcher=process.DataFirstProcess(admission)))
 assert len(calls)==2 and list((state/'data-first').iterdir())==before


def test_unowned_namespace_rejected_without_touching_foreign_sqlite(tmp_path,monkeypatch):
 import grid.data_first_runtime as module
 grant,readmit,state=fixture(tmp_path);root=state/'data-first';root.mkdir();foreign=root/'foreign.sqlite3';foreign.write_bytes(b'FOREIGN')
 monkeypatch.setattr(module,'windows_root',lambda:str(tmp_path))
 with pytest.raises(Exception):module.ProtectedDataFirstAdmission(grant,readmit).process_spec()
 assert foreign.read_bytes()==b'FOREIGN' and list(root.iterdir())==[foreign]

def test_parent_continuation_rejects_workspace_marker_mutation(tmp_path,monkeypatch):
 import grid.data_first_runtime as module
 grant,readmit,state=fixture(tmp_path);monkeypatch.setattr(module,'windows_root',lambda:str(tmp_path))
 admission=module.ProtectedDataFirstAdmission(grant,readmit);admission.process_spec()
 marker=state/'data-first'/'data-first-owned.json';marker.write_bytes(marker.read_bytes()+b' ')
 with pytest.raises(Exception):admission.require_current()


def test_waiting_consumer_survives_initial_admission_failure_and_advertises_only_live_task(monkeypatch):
 import asyncio
 import grid.worker as module
 class Store:
  def __init__(self,*a,**kw):pass
 for name in ('Storage','MicroEventStorage','LocalControlJournal','ControlSnapshotRing','CommandReceiptStore'):monkeypatch.setattr(module,name,Store)
 class Admission:
  def runtime_capability(self):return {'protocol':'grid.stratt-data-first.v1','source_commit':'a'*40}
 class Launcher:
  calls=0
  def __init__(self,a):pass
  def require_admitted(self):
   self.calls+=1
   if self.calls==1:raise ValueError('transient')
   return True
 monkeypatch.setattr('grid.data_first_process.DataFirstProcess',Launcher)
 async def run():
  worker=module.Worker(data_first_admission=Admission());entered=asyncio.Event();release=asyncio.Event()
  async def waiting():entered.set();await release.wait()
  worker._data_first_loop=waiting
  assert worker.data_first_capability() is None and worker.data_first_launcher.calls==0
  worker._start_data_first_consumer();await entered.wait()
  assert worker.data_first_capability() is None
  assert worker.data_first_capability()['source_commit']=='a'*40
  release.set();await worker.data_first_task
  assert worker.data_first_capability() is None
 asyncio.run(run())


def test_source_owner_exception_requires_full_real_supplier_and_exact_grid_binding(tmp_path,monkeypatch):
 import types
 from grid import coordinator
 from grid.data_first_runtime import ProtectedDataFirstAdmission
 from grid.owned_worker_service import OwnedWorkerService
 grant,readmit,_=fixture(tmp_path);calls=[]
 def observe(g):calls.append(True);return readmit(g)
 source=grant.code_root/'sources/grid';monkeypatch.setattr(coordinator,'_MODULE_SOURCE_ROOT',source)
 admission=ProtectedDataFirstAdmission(grant,observe);service=OwnedWorkerService(data_first_admission=admission)
 assert service._owner_admitted_source_root('d'*40)==source and len(calls)==1
 assert service._owner_admitted_source_root('d'*40)==source and len(calls)==2
 with pytest.raises(Exception):service._owner_admitted_source_root('e'*40)
 monkeypatch.setattr(coordinator,'_MODULE_SOURCE_ROOT',source.parent)
 with pytest.raises(Exception):service._owner_admitted_source_root('d'*40)
 monkeypatch.setenv('UNIFIED_OWNER_ADMITTED_ROOT',str(source))
 assert OwnedWorkerService()._owner_admitted_source_root('d'*40) is None
 fake=types.SimpleNamespace(owner_admitted_grid_root=lambda expected:source)
 assert OwnedWorkerService(data_first_admission=fake)._owner_admitted_source_root('d'*40) is None
