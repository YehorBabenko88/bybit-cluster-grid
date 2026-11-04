"""Bounded fixed DataFirst process/IPC primitive, not deployment readiness.

The admission object belongs to protected runtime. Job JSON cannot supply an
executable, source root, environment, workspace or network authorization. The
fixed Stratt main remains BLOCKED until protected scheduler provisioning exists.
Windows containment reuses WindowsJob; other platforms are blocked before claim
until strong whole-tree containment is implemented.
"""
import asyncio,copy,hashlib,json,os,re,secrets,shutil,stat,tempfile
from pathlib import Path
import psutil
from .data_first_jobs import KIND,STATES,request_sha,validate_request
from .ml_process_supervisor import terminate_process_tree

SCHEMA='grid.data-first.process.v1'
MAX_FRAME=1048576
CODES=frozenset(('PROCESS_ADMISSION_REQUIRED','PROCESS_PLATFORM_UNQUALIFIED','PROCESS_ADMISSION_REVOKED','PROCESS_SOURCE_REJECTED','PROCESS_PROTOCOL_REJECTED','PROCESS_LEASE_FENCED','PROCESS_LEASE_UNAVAILABLE','PROCESS_TIMEOUT','PROCESS_MEMORY','PROCESS_CHILD_FAILED','PROCESS_PIPE_EOF','PROCESS_OUTPUT_REJECTED','PROCESS_CLEANUP_UNAVAILABLE','PROCESS_PROVISIONING_NOT_IMPLEMENTED'))

class ProcessBlocked(RuntimeError):
 def __init__(self,code='PROCESS_PROTOCOL_REJECTED'):
  self.code=code if code in CODES else 'PROCESS_PROTOCOL_REJECTED';super().__init__(self.code)

def need(ok,code='PROCESS_PROTOCOL_REJECTED'):
 if not ok:raise ProcessBlocked(code)

def _hex(value,n=64):return type(value) is str and re.fullmatch('[a-f0-9]{'+str(n)+'}',value) is not None

def _body(op,body):
 need(type(body) is dict)
 if op=='INIT':need(set(body)=={'job'} and type(body['job']) is dict)
 elif op=='RENEW':need(body=={})
 elif op=='CHECKPOINT':need(set(body)=={'sequence','state','checkpoint'} and type(body['sequence']) is int and 1<=body['sequence']<2**63 and body['state'] in STATES and type(body['checkpoint']) is dict)
 elif op=='DONE':need(set(body)=={'sequence','state','sha256'} and type(body['sequence']) is int and body['sequence']>=1 and body['state'] in ('COMPLETED','FAILED','BLOCKED','YIELDED') and _hex(body['sha256']))
 elif op=='ERROR':need(set(body)=={'code'} and body['code'] in CODES)
 elif op=='ACK':need(set(body)=={'op','value'} and body['op'] in ('RENEW','CHECKPOINT') and type(body['value']) is dict)
 else:need(False)

def encode_frame(nonce,sequence,op,body):
 try:
  need(_hex(nonce) and type(sequence) is int and 0<=sequence<2**31 and (op=='INIT')==(sequence==0));_body(op,body)
  raw=json.dumps(dict(schema=SCHEMA,nonce=nonce,seq=sequence,op=op,body=body),sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
  need(len(raw)<=MAX_FRAME);return raw
 except ProcessBlocked:raise
 except Exception:raise ProcessBlocked() from None

def decode_frame(raw,nonce,sequence):
 try:
  need(type(raw) is bytes and 0<len(raw)<=MAX_FRAME and raw.endswith(b'\n'))
  def unique(pairs):
   out={}
   for key,value in pairs:need(key not in out);out[key]=value
   return out
  frame=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:need(False))
  need(type(frame) is dict and set(frame)=={'schema','nonce','seq','op','body'} and frame['schema']==SCHEMA and frame['nonce']==nonce and frame['seq']==sequence)
  need(encode_frame(nonce,sequence,frame['op'],frame['body'])==raw);return frame['op'],frame['body']
 except ProcessBlocked:raise
 except Exception:raise ProcessBlocked() from None

def _local(value):
 need(type(value) is str and not value.startswith(('//',chr(92))),'PROCESS_SOURCE_REJECTED')
 path=Path(value);need(path.is_absolute() and '..' not in path.parts,'PROCESS_SOURCE_REJECTED')
 for part in (*reversed(path.parents),path):
  info=part.lstat();need(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&1024,'PROCESS_SOURCE_REJECTED')
 need(str(path.resolve(strict=True))==str(path),'PROCESS_SOURCE_REJECTED');return path

def _pinned(value,digest,limit):
 path=_local(value);info=path.stat();need(_hex(digest) and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<=limit,'PROCESS_SOURCE_REJECTED')
 with path.open('rb') as stream:
  raw=stream.read(limit+1);after=os.fstat(stream.fileno())
 fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_nlink)
 need(fields(info)==fields(after)==fields(path.stat()) and hashlib.sha256(raw).hexdigest()==digest,'PROCESS_SOURCE_REJECTED');return path

class DataFirstProcess:
 """Only protected runtime may provide this admission boundary.

 require_current() is the runtime's live kernel/profile/owner gate, not a JSON
 readiness flag. process_spec() returns its already admitted immutable inputs.
 Test doubles of that boundary establish software behavior only.
 """
 def __init__(self,admission):self._admission=admission;self._spec_pin=None;self._poisoned=False
 def _current(self):
  need(not self._poisoned,'PROCESS_CLEANUP_UNAVAILABLE')
  need(self._admission is not None and not isinstance(self._admission,dict) and callable(getattr(self._admission,'require_current',None)) and callable(getattr(self._admission,'process_spec',None)),'PROCESS_ADMISSION_REQUIRED')
  try:need(self._admission.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  except ProcessBlocked:raise
  except Exception:raise ProcessBlocked('PROCESS_ADMISSION_REVOKED') from None
 def require_admitted(self):
  need(os.name=='nt','PROCESS_PLATFORM_UNQUALIFIED')
  self._current()
  try:
   spec=copy.deepcopy(self._admission.process_spec())
   need(type(spec) is dict and set(spec)=={'python','python_sha256','bootstrap','bootstrap_sha256','source_root','source_commit','worker_sha256','dependency_roots','workspace_root','system_root','module_version','release_id','network_scope','timeout_seconds','ram_limit_mb'},'PROCESS_ADMISSION_REQUIRED')
   need(spec['network_scope']=='PUBLIC_GET_ONLY_RESEARCH' and _hex(spec['source_commit'],40),'PROCESS_ADMISSION_REQUIRED')
   need(type(spec['timeout_seconds']) in (int,float) and 1<=spec['timeout_seconds']<=300 and type(spec['ram_limit_mb']) is int and 64<=spec['ram_limit_mb']<=65536,'PROCESS_ADMISSION_REQUIRED')
   need(type(spec['module_version']) is str and re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]{1,40})?',spec['module_version']) and type(spec['release_id']) is str and re.fullmatch('[A-Za-z0-9_.:-]{1,128}',spec['release_id']),'PROCESS_ADMISSION_REQUIRED')
   _pinned(spec['python'],spec['python_sha256'],64*1024*1024);_pinned(spec['bootstrap'],spec['bootstrap_sha256'],1048576)
   source=_local(spec['source_root']);workspace=_local(spec['workspace_root']);need(source.is_dir() and workspace.is_dir() and source!=workspace and source not in workspace.parents and workspace not in source.parents,'PROCESS_SOURCE_REJECTED')
   _pinned(str(source/'strattester/engine/grid_data_first_worker.py'),spec['worker_sha256'],1048576)
   need(type(spec['dependency_roots']) is list and len(spec['dependency_roots'])<=32 and len(set(spec['dependency_roots']))==len(spec['dependency_roots']),'PROCESS_SOURCE_REJECTED')
   for value in spec['dependency_roots']:need(_local(value).is_dir(),'PROCESS_SOURCE_REJECTED')
   if spec['system_root'] is not None:need(_local(spec['system_root']).is_dir(),'PROCESS_SOURCE_REJECTED')
   pin=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
   need(self._spec_pin is None or self._spec_pin==pin,'PROCESS_ADMISSION_REVOKED');self._current();self._spec_pin=pin;self._spec=spec;return True
  except ProcessBlocked:raise
  except Exception:raise ProcessBlocked('PROCESS_SOURCE_REJECTED') from None
 async def run_supervised(self,job,client):
  self.require_admitted();spec=self._spec;need(type(job) is dict and job.get('job_type')==KIND)
  try:validate_request(job['payload'])
  except Exception:raise ProcessBlocked('PROCESS_SOURCE_REJECTED') from None
  need(job['payload']['source_commit']==spec['source_commit'],'PROCESS_SOURCE_REJECTED')
  need(set(job)<={'id','job_type','payload','lease_owner','lease_generation','lease_until','attempts','domain_state'} and type(job.get('id')) is str and 1<=len(job['id'])<=128 and type(job.get('lease_owner')) is str and 1<=len(job['lease_owner'])<=128 and type(job.get('lease_generation')) is int and job['lease_generation']>=1)
  job=copy.deepcopy(job);nonce=secrets.token_hex(32);initial=encode_frame(nonce,0,'INIT',{'job':job});request_pin=request_sha(job['payload'])
  parent=_local(spec['workspace_root']);parent_id=(parent.stat().st_dev,parent.stat().st_ino)
  workspace=Path(tempfile.mkdtemp(prefix='data-first-',dir=parent));workspace_id=(workspace.stat().st_dev,workspace.stat().st_ino);(workspace/'cache').mkdir()
  proc=None;owned_job=None;birth=None;tasks=[]
  def close_job():
   nonlocal owned_job
   if owned_job is not None:
    owned=owned_job
    try:
     wait=getattr(owned,'terminate_and_wait',None)
     need(callable(wait) and wait(5) is True,'PROCESS_CLEANUP_UNAVAILABLE')
    except BaseException:
     self._poisoned=True
     try:owned.close() # best effort only; no empty proof is asserted
     except BaseException:pass
     owned_job=None
     raise ProcessBlocked('PROCESS_CLEANUP_UNAVAILABLE') from None
    owned_job=None
  try:
   env={'TEMP':str(workspace),'TMP':str(workspace),'UNIFIED_MODULE_ID':'strattester','UNIFIED_MODULE_VERSION':spec['module_version'],'UNIFIED_RELEASE_ID':spec['release_id'],'UNIFIED_INSTANCE_TOKEN':secrets.token_hex(32),'UNIFIED_PRIVATE_CACHE_ROOT':str(workspace/'cache'),'UNIFIED_ORDER_MODE':'PAPER_ONLY','UNIFIED_DEPLOYMENT_MODE':'LAB_SIMULATION'}
   if spec['system_root'] is not None:env.update(SystemRoot=spec['system_root'],WINDIR=spec['system_root'])
   argv=[spec['python'],'-I','-S','-B',spec['bootstrap'],'--source-root',spec['source_root']]
   for value in spec['dependency_roots']:argv+=['--dependency-root',value]
   argv+=['--module','strattester.engine.grid_data_first_worker']
   self._current()
   options={'creationflags':4} if os.name=='nt' else {'start_new_session':True}
   proc=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env,cwd=str(workspace),limit=MAX_FRAME+1,**options)
   birth=psutil.Process(proc.pid).create_time()
   if os.name=='nt':
    from .ml_windows_job import WindowsJob
    owned_job=WindowsJob(proc.pid,resume_primary_thread=True)
   proc.stdin.write(initial);await proc.stdin.drain()
   async def exchange():
    ipc_sequence=1;last=None
    while True:
     raw=await proc.stdout.readline()
     if not raw:raise ProcessBlocked('PROCESS_PIPE_EOF')
     op,body=decode_frame(raw,nonce,ipc_sequence)
     self._current()
     if op=='ERROR':raise ProcessBlocked(body['code'])
     if op=='DONE':
      need(last is not None and body=={'sequence':last[0],'state':last[1]['state'],'sha256':last[1]['sha256']});return last[1]
     need(op in ('RENEW','CHECKPOINT'))
     try:
      if op=='RENEW':
       renewed=await client.renew(copy.deepcopy(job));need(type(renewed) is dict and set(renewed)=={'ok'} and renewed['ok'] is True,'PROCESS_LEASE_FENCED');value={'valid':True}
      else:
       value=await client.checkpoint(copy.deepcopy(job),body['sequence'],body['state'],body['checkpoint'])
       need(type(value) is dict and set(value)=={'accepted','sha256','state','request_sha256'} and value['accepted'] is True and value['state']==body['state'] and value['request_sha256']==request_pin,'PROCESS_LEASE_FENCED')
       expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest();need(value['sha256']==expected,'PROCESS_LEASE_FENCED');last=(body['sequence'],copy.deepcopy(value))
     except ProcessBlocked:raise
     except Exception:raise ProcessBlocked('PROCESS_LEASE_UNAVAILABLE') from None
     proc.stdin.write(encode_frame(nonce,ipc_sequence,'ACK',{'op':op,'value':value}));await proc.stdin.drain();ipc_sequence+=1
   async def stderr():
    if await proc.stderr.read(1):raise ProcessBlocked('PROCESS_OUTPUT_REJECTED')
   async def monitor():
    while proc.returncode is None:
     self._current()
     try:current=psutil.Process(proc.pid)
     except psutil.NoSuchProcess:
      await asyncio.wait_for(proc.wait(),timeout=5);break
     need(current.create_time()==birth,'PROCESS_CHILD_FAILED')
     rss=current.memory_info().rss
     for child in current.children(recursive=True):
      try:rss+=child.memory_info().rss
      except psutil.NoSuchProcess:pass
     need(rss<=spec['ram_limit_mb']*1024*1024,'PROCESS_MEMORY');await asyncio.sleep(.1)
    close_job()
   protocol=asyncio.create_task(exchange());tasks=[protocol,asyncio.create_task(stderr()),asyncio.create_task(monitor())]
   async def wait_protocol():
    remaining=set(tasks)
    while protocol in remaining:
     done,_=await asyncio.wait(remaining,return_when=asyncio.FIRST_COMPLETED)
     for task in done:
      task.result();remaining.remove(task)
     if protocol in done:return protocol.result()
   try:receipt=await asyncio.wait_for(wait_protocol(),timeout=spec['timeout_seconds'])
   except asyncio.TimeoutError:raise ProcessBlocked('PROCESS_TIMEOUT') from None
   await asyncio.wait_for(proc.wait(),timeout=5);need(proc.returncode==0,'PROCESS_CHILD_FAILED');close_job()
   await asyncio.wait_for(asyncio.gather(*tasks[1:]),timeout=5)
   need(not await asyncio.wait_for(proc.stdout.read(1),timeout=5))
   return {'state':receipt['state'],'receipt':receipt,'scope':'SUPERVISED_PROCESS_PRIMITIVE','deployment':'NOT_QUALIFIED'}
  except asyncio.CancelledError:raise
  except ProcessBlocked:raise
  except Exception:raise ProcessBlocked('PROCESS_CHILD_FAILED') from None
  finally:
   async def cleanup():
    for task in tasks:
     if not task.done():task.cancel()
    await asyncio.gather(*tasks,return_exceptions=True)
    try:
     try:close_job()
     except ProcessBlocked:pass # still join the root, then retain scratch/fence retry
     if proc is not None and proc.returncode is None:
      # Job close can kill the owned root before asyncio observes its exit.
      # Join its retained process object; never enumerate/terminate a reused PID.
      try:current=psutil.Process(proc.pid)
      except psutil.NoSuchProcess:await asyncio.wait_for(proc.wait(),timeout=5)
      else:
       need(birth is None or current.create_time()==birth,'PROCESS_CLEANUP_UNAVAILABLE')
       await asyncio.wait_for(terminate_process_tree(proc,grace_seconds=2),timeout=5)
     if proc is not None:await asyncio.wait_for(proc.wait(),timeout=5)
     need(not self._poisoned,'PROCESS_CLEANUP_UNAVAILABLE')
     need((_local(str(parent)).stat().st_dev,parent.stat().st_ino)==parent_id and (_local(str(workspace)).stat().st_dev,workspace.stat().st_ino)==workspace_id,'PROCESS_CLEANUP_UNAVAILABLE')
     count=0
     for directory,dirs,files in os.walk(workspace,followlinks=False):
      count+=len(dirs)+len(files);need(count<=4096,'PROCESS_CLEANUP_UNAVAILABLE')
      for name in (*dirs,*files):_local(str(Path(directory)/name))
     shutil.rmtree(workspace)
    except BaseException:
     self._poisoned=True;raise ProcessBlocked('PROCESS_CLEANUP_UNAVAILABLE') from None
   cleanup_task=asyncio.create_task(cleanup());cancelled=False
   while True:
    try:await asyncio.shield(cleanup_task);break
    except asyncio.CancelledError:cancelled=True
   if cancelled:raise asyncio.CancelledError
