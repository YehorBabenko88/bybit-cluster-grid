"""Actual Git/ASGI source checks; modeled admission, no database or listener."""
import asyncio,hashlib,importlib,os,shutil,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx,pytest

@pytest.fixture
def bound(monkeypatch,tmp_path):
 from grid import coordinator as c
 root=tmp_path/'source';root.mkdir();(root/'owner.py').write_bytes(b'owned\n')
 git=Path(shutil.which('git')).resolve()
 def run(*args):return subprocess.check_output([str(git),'-C',str(root),*args],stderr=subprocess.DEVNULL).decode().strip()
 run('init','-q');run('config','core.autocrlf','false');run('add','.');run('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
 head=run('rev-parse','HEAD');calls=[];state={'live':True}
 def scope(module,actual,commit):
  calls.append((module,actual,commit))
  if (module,actual,commit)!=('grid',root,head):raise ValueError('SOURCE_UNAVAILABLE')
  return root
 admission=SimpleNamespace(require_current=lambda:state['live'],source_scope=scope,git_executable=str(git),git_sha256=hashlib.sha256(git.read_bytes()).hexdigest())
 for key,value in zip(c._OWNED_MODULE_ENV,('grid','1.2.3','test-release','a'*64,head)):monkeypatch.setenv(key,value)
 monkeypatch.setattr(c,'_MODULE_SOURCE_ROOT',root);monkeypatch.setattr(c,'_owned_module_binding',None)
 # State proxies attributes through _state, not its instance __dict__.
 # Restore the mapping itself so pytest 9.2 cannot undo the same proxy twice.
 monkeypatch.setitem(c.app.state._state,'owned_source_admission',None)
 monkeypatch.setattr(c,'settings',SimpleNamespace(grid_coordination_mode='legacy'));monkeypatch.setattr(c,'control_leader',None)
 queries=[]
 async def fetchval(query):queries.append(query);return 1
 monkeypatch.setattr(c,'db',SimpleNamespace(pool=SimpleNamespace(fetchval=fetchval)))
 return c,root,head,admission,state,calls,queries

def test_default_foreign_owner_denied_and_exact_scope_has_no_config_mutation(bound,monkeypatch):
 c,root,head,admission,state,calls,_=bound;config=(root/'.git/config').read_bytes();real=subprocess.Popen;commands=[]
 def foreign(command,**kwargs):
  commands.append(command);kwargs['env']=dict(kwargs['env'],GIT_TEST_ASSUME_DIFFERENT_OWNER='1');return real(command,**kwargs)
 with patch.object(subprocess,'Popen',side_effect=foreign):
  assert c._owned_source_is_clean(head) is False
  assert c._owned_source_is_clean(head,startup_admission=admission) is True
 assert calls and (root/'.git/config').read_bytes()==config
 for command in commands[1:]:
  assert command[0]==admission.git_executable
  assert 'safe.directory=' in command and 'safe.directory='+str(root) in command

@pytest.mark.parametrize('kind',['json','revoked','nonliteral','scope','git','head'])
def test_invalid_admission_rejected_before_git(bound,kind):
 c,root,head,admission,state,_,_=bound
 if kind=='json':admission={'authorized':True}
 elif kind=='revoked':state['live']=False
 elif kind=='nonliteral':state['live']=1
 elif kind=='scope':admission.source_scope=lambda *args:root.parent
 elif kind=='git':admission.git_sha256='f'*64
 else:head='f'*40
 with patch.object(subprocess,'Popen',side_effect=AssertionError('must reject before process')):
  assert c._owned_source_is_clean(head,startup_admission=admission) is False

def test_revocation_before_next_git_and_final_binding_blocks(bound,monkeypatch):
 c,root,head,admission,state,_,_=bound;real=subprocess.Popen;commands=[]
 def revoke(command,**kwargs):
  commands.append(command);child=real(command,**kwargs);state['live']=False;return child
 with patch.object(subprocess,'Popen',side_effect=revoke):
  assert c._owned_source_is_clean(head,startup_admission=admission) is False
 assert len(commands)==1
 state['live']=True;monkeypatch.setattr(c.app.state,'owned_source_admission',admission)
 def source(*args,**kwargs):state['live']=False;return True
 monkeypatch.setattr(c,'_owned_source_is_clean',source)
 with pytest.raises(RuntimeError,match='Owned module'):
  asyncio.run(c._initialize_owned_module_health())
 assert c._owned_module_binding is None

def test_revoked_live_health_does_not_probe_database(bound,monkeypatch):
 c,_,_,admission,state,_,queries=bound;monkeypatch.setattr(c.app.state,'owned_source_admission',admission)
 async def scenario():
  await c._initialize_owned_module_health();state['live']=False
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app),base_url='http://model') as client:
   response=await client.get('/internal/v2/module/health',headers={'Authorization':'Bearer '+'a'*64})
  assert response.status_code==503 and queries==[]
 asyncio.run(scenario())

@pytest.mark.parametrize('when',['removed','during-query'])
def test_bound_admission_cannot_disappear_or_be_revoked_during_health(bound,monkeypatch,when):
 c,_,_,admission,state,_,queries=bound;monkeypatch.setattr(c.app.state,'owned_source_admission',admission)
 async def scenario():
  await c._initialize_owned_module_health()
  if when=='removed':c.app.state.owned_source_admission=None
  else:
   async def fetchval(query):state['live']=False;queries.append(query);return 1
   c.db.pool.fetchval=fetchval
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app),base_url='http://model') as client:
   response=await client.get('/internal/v2/module/health',headers={'Authorization':'Bearer '+'a'*64})
  assert response.status_code==503
  if when=='removed':assert queries==[]
 asyncio.run(scenario())

@pytest.mark.parametrize('started',[True,False])
def test_fixed_entry_runs_one_loopback_existing_app_after_live_scope(bound,monkeypatch,started):
 from grid import owned_control_service as entry
 c,root,head,admission,state,_,_=bound
 monkeypatch.setattr(entry,'__file__',str(root/'grid/owned_control_service.py'))
 monkeypatch.setattr(c.settings,'role','coordinator',raising=False)
 seen=[]
 class Config:
  def __init__(self,app,**kwargs):
   assert c.app.state.owned_source_admission is admission
   seen.append((app,kwargs))
 class Server:
  def __init__(self,config):self.config=config;self.started=started
  def run(self):seen.append('MODELED_NO_LISTENER')
 uvicorn=SimpleNamespace(Config=Config,Server=Server)
 real=importlib.import_module
 def imports(name):
  assert admission.require_current() is True
  return uvicorn if name=='uvicorn' else real(name)
 with patch.object(importlib,'import_module',side_effect=imports):
  if started:assert entry.main(['--execute','--port','8766'],startup_admission=admission)==0
  else:
   with pytest.raises(ValueError,match='startup'):entry.main(['--execute','--port','8766'],startup_admission=admission)
 assert seen==[(c.app,dict(host='127.0.0.1',port=8766,access_log=False,workers=1,reload=False)),'MODELED_NO_LISTENER']

def test_fixed_entry_rejects_missing_admission_before_application_import():
 assert importlib.util.find_spec('grid.owned_control_service') is not None,'fixed protected CONTROL entry missing'
 from grid import owned_control_service as entry
 with patch.object(importlib,'import_module',side_effect=AssertionError('no dependency/application import')):
  with pytest.raises(ValueError):entry.main(['--execute','--port','8766'])

def test_fixed_entry_rejects_wrong_arguments_before_application_import():
 assert importlib.util.find_spec('grid.owned_control_service') is not None,'fixed protected CONTROL entry missing'
 from grid import owned_control_service as entry
 with patch.object(importlib,'import_module',side_effect=AssertionError('no dependency/application import')):
  for argv in (['--execute','--port','0'],['--execute','--port','8766','--reload'],['--port','8766','--execute']):
   with pytest.raises(ValueError):entry.main(argv,startup_admission=object())
