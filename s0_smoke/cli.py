"""Explicit operator actions. Plan is pure; no physical authorization is inferred."""
import argparse,asyncio,hashlib,importlib.abc,json,os,re,shutil,socket,sys,time,zipfile
from contextlib import ExitStack
from pathlib import Path
from .policy import need,load_json,canonical,validate_plan,forbidden_environment,import_allowed
from .storage import Journal,write_new,read_small,request_stop,stop_requested

class Parser(argparse.ArgumentParser):
 def error(self,message):raise ValueError('S0_ARGUMENTS_BLOCKED')

class PublicOnlyImports(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  need(import_allowed(fullname),'S0_PRODUCTION_IMPORT_BLOCKED');return None

def install_guard():
 need(all(import_allowed(n) for n in sys.modules),'S0_ALREADY_IMPORTED_PRODUCTION_MODULE')
 sys.meta_path.insert(0,PublicOnlyImports())

def host():
 import ctypes
 k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetComputerNameW.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)];k.GetComputerNameW.restype=ctypes.c_int
 size=ctypes.c_uint32(256);buf=ctypes.create_unicode_buffer(256);need(k.GetComputerNameW(buf,ctypes.byref(size))!=0,'S0_HOST_QUERY_BLOCKED');return buf.value.upper()

def root_id(root,sid):
 from .windows import Win32
 api=Win32();h=api.open(str(root),True)
 try:return list(api.inspect(h)['identity'])
 finally:api.close(h)

def marker(root,context,sid,pin,parent):
 from .windows import create_fresh_file,MutableFile
 with MutableFile(Path(root)/'stop.json',sid) as lease:stop_id=list(lease.identity)
 value=dict(schema=1,**context,package_sha256=pin,root_id=root_id(root,sid),stop_id=stop_id)
 if parent.mode=='UserProfileV1':value.update(parent.binding())
 create_fresh_file(Path(root)/'prepared.json',sid,canonical(value))

def prepared(root,c,sid,pin,parent):
 from .windows import MutableFile
 v=load_json(read_small(root,'prepared.json'))
 fields={'schema','head','run_id','role','package_sha256','root_id','stop_id'}
 if parent.mode=='UserProfileV1':
  binding=parent.binding();fields.update(binding);need(all(v.get(k)==value for k,value in binding.items()),'S0_PARENT_PROOF_DRIFT')
 need(set(v)==fields and type(v['schema']) is int and v['schema']==1 and all(v[k]==x for k,x in local_context(c).items()) and v['package_sha256']==pin and v['root_id']==root_id(root,sid),'S0_PREPARED_ROOT_IDENTITY_BLOCKED')
 with MutableFile(Path(root)/'stop.json',sid) as lease:need(v['stop_id']==list(lease.identity),'S0_STOP_IDENTITY_BLOCKED')
 return v

def local_context(c):return dict(head=c['plan']['head'],run_id=c['plan']['run_id'],role=c['role'])

def prepare(args,identity,parent):
 from .windows import Custody,create_fresh_root,create_fresh_file
 from .materials import materials,validate_config,TLS_FILES
 local=Path(parent.path).absolute();input_path=Path(args.config).absolute();relative=input_path.relative_to(local);need(len(relative.parts) in (2,3) and re.fullmatch('GridS0Input-[0-9a-f-]{36}',relative.parts[0]) and input_path.name in ('s0-plan.json','config.json'),'S0_PROTECTED_INPUT_NAMESPACE_REQUIRED');need(len(relative.parts)==2 or relative.parts[1]=='PC4');need(Path(args.root).absolute().parent==local,'S0_PRIVATE_PROFILE_ROOT_REQUIRED')
 raw=read_small(input_path.parent,input_path.name);v=load_json(raw)
 with Custody(Path(args.config).parent,identity.sid,[args.config]):
  need(read_small(Path(args.config).parent,Path(args.config).name)==raw)
  if v.get('profile')=='PHYSICAL_SMOKE_S0' and 'role' in v:
   c=validate_config(raw,args.expected_head,args.expected_package_sha);p=c['plan'];need(c['role']=='PC4' and host()==p['hostnames']['PC4'] and identity.sid==p['operator_sids']['PC4'])
   incoming=Path(args.config).parent;files={n:read_small(incoming,n) for n in TLS_FILES}
   for n,h in c['files'].items():need(hashlib.sha256(files[n]).hexdigest()==h)
   files.update({'config.json':raw,'stop.json':canonical(dict(local_context(c),stop=False))});roles={'PC4':files}
  else:
   p=validate_plan(v,args.expected_head);need(host()==p['hostnames']['LS5'] and identity.sid==p['operator_sids']['LS5']);roles=None
  root=Path(args.root);need(root.name=='GridS0-'+p['run_id'],'S0_FRESH_ROOT_NAME_REQUIRED')
  create_fresh_root(root,identity.sid);create_fresh_root(root/'temp',identity.sid)
  if roles is None:roles=materials(p,args.expected_head,args.expected_package_sha)
  for role,files in roles.items():
   child=root/role;create_fresh_root(child,identity.sid);create_fresh_root(child/'temp',identity.sid)
   for name,data in files.items():create_fresh_file(child/name,identity.sid,data)
   if host()==p['hostnames'][role] and identity.sid==p['operator_sids'][role]:marker(child,dict(head=p['head'],run_id=p['run_id'],role=role),identity.sid,args.expected_package_sha,parent)
 return dict(status='S0_PREPARED_NOT_EXECUTED',roles=list(roles),private_material='RETAINED_IN_PROTECTED_ROLE_DIRECTORIES_NEVER_EVIDENCE',s0_execute=False,g1_execute=False,cleanup=False)

def finish(root,c,result,error,manifest,pin):
 import xml.etree.ElementTree as E
 stats=result.get('stats') or {};observed=error is None and result.get('reason')=='WINDOW_COMPLETE' and result.get('elapsed_ms',0)>=240000 and result.get('registered') is True and result.get('heartbeats',0)>=3 and stats.get('trade_count',0)>0 and stats.get('book_updates',0)>0 and result.get('final') is True and (c['role']=='LS5' or result.get('last_market_age_ms',999999)<=5000)
 summary=dict(schema=1,**local_context(c),tree=manifest['tree'],package_sha256=pin,scope='S0_PUBLIC_ONLY_NOT_GRID_ACCEPTANCE',status='PUBLIC_SMOKE_OBSERVED' if observed else 'BLOCKED_OR_PARTIAL',result=result,error=error,g1_execute=False,physical_sid_acl='0/10 NOT_RUN',cleanup_authorized=False,deployment='NO-GO')
 write_new(root,'summary.json',canonical(summary));suite=E.Element('testsuite',dict(name='physical_smoke_s0',tests='1',failures='0' if observed else '1',errors='0',skipped='0',head=c['plan']['head'],run_id=c['plan']['run_id']));case=E.SubElement(suite,'testcase',dict(name='public_only_s0'))
 if not observed:E.SubElement(case,'failure',dict(message='S0_NOT_ACCEPTED'))
 write_new(root,'results.xml',E.tostring(suite,encoding='utf-8',xml_declaration=True))
 files={}
 for n in ('events.jsonl','market.jsonl','claim.json','summary.json','results.xml','prepared.json'):
  if (Path(root)/n).is_file():files[n]=hashlib.sha256(read_small(root,n,67108864)).hexdigest()
 write_new(root,'sha256.json',canonical(dict(schema=1,**local_context(c),package_sha256=pin,files=files,g1_execute=False,cleanup_authorized=False)))
 return summary

def execute(args,c,identity,manifest,guard):
 from .windows import create_fresh_file,ExclusiveFile,MutableFile
 from .lifecycle import arm_deadline,runtime_budget
 from .runtime import coordinator,worker
 arm_deadline();root=Path(args.root);ctx=local_context(c);need(not stop_requested(root,ctx),'S0_PREEXISTING_STOP')
 claim=dict(ctx,pid=identity.pid,creation_filetime=identity.creation_filetime,operator_sid=identity.sid,elevated=identity.elevated,integrity=identity.integrity,admin_enabled=identity.admin_enabled,enabled_privileges=list(identity.enabled_privileges),image_sha256=hashlib.sha256(Path(identity.image_path).read_bytes()).hexdigest())
 create_fresh_file(root/'claim.json',identity.sid,canonical(claim))
 result={};error=None
 with ExclusiveFile(root/'claim.json',identity.sid) as run_lock,MutableFile(root/'stop.json',identity.sid) as stop_lock,Journal(root,'events.jsonl',ctx) as events,ExitStack() as stack:
  market=stack.enter_context(Journal(root,'market.jsonl',ctx,limit=67108864)) if c['role']=='PC4' else None
  checked=0.
  def protected():
   nonlocal checked
   run_lock.guard();stop_lock.guard()
   if time.monotonic()-checked>=1:need(shutil.disk_usage(root).free>=134217728,'S0_DISK_RESERVE_STOP');guard();checked=time.monotonic()
  events.add('started',claim)
  try:
   budget=runtime_budget()
   coro=coordinator(c,root,events,protected,seconds=budget) if c['role']=='LS5' else worker(c,root,events,market,protected,seconds=budget)
   result=asyncio.run(asyncio.wait_for(coro,budget+1));protected()
  except Exception as exc:error=type(exc).__name__;events.add('blocked',{'error_class':error})
  events.add('finished',dict(result=result,error=error));events.close()
  if market is not None:market.close()
  return finish(root,c,result,error,manifest,args.expected_package_sha)

def dispatch(args):
 from .windows import current_identity,require_operator,Custody,MutableFile,ExclusiveFile,port_available
 from .package import verify_package
 import tempfile
 tempfile.tempdir=str(Path(args.root).absolute()/'temp')
 from .materials import validate_config,TLS_FILES
 need(sys.platform=='win32','S0_WINDOWS_ONLY');forbidden_environment(os.environ);need(all(Path(os.environ.get(k,'')).absolute()==Path(args.root).absolute()/'temp' for k in ('TEMP','TMP')),'S0_OWN_TEMP_REQUIRED');identity=current_identity();require_operator(identity)
 from .profile import ParentLease
 with ParentLease(args.parent_scope,identity.sid) as parent:
  local=Path(parent.path).absolute();package=Path(args.package_root).absolute();need(package.parent==local and re.fullmatch('GridS0Package-[0-9a-f-]{36}',package.name),'S0_PRIVATE_PACKAGE_NAMESPACE_REQUIRED');need(shutil.disk_usage(local).free>=536870912,'S0_DISK_RESERVE_REQUIRED');archive=Path(args.package_zip).absolute();need(Path(identity.image_path).absolute()==package/'runtime'/'python.exe','S0_BUNDLED_INTERPRETER_REQUIRED');manifest=verify_package(package,archive,args.expected_head,args.expected_package_sha)
  pins=[package/n for n in manifest['files']]+[package/'s0-package.json',archive]
  with Custody(package,identity.sid,pins) as source:
   verify_package(package,archive,args.expected_head,args.expected_package_sha);source.guard()
   if args.action=='prepare':return prepare(args,identity,parent)
   root=Path(args.root).absolute();need(Path(args.config).absolute()==root/'config.json','S0_CONFIG_MUST_BE_OWN_ROLE_CONFIG')
   c=validate_config(read_small(root,'config.json'),args.expected_head,args.expected_package_sha);role=c['role'];need(host()==c['plan']['hostnames'][role] and identity.sid==c['plan']['operator_sids'][role],'S0_HOST_SID_MISMATCH')
   need(root.parent.parent==local and root.name==role and root.parent.name=='GridS0-'+c['plan']['run_id'],'S0_ROLE_ROOT_NAME_BLOCKED')
   with Custody(root,identity.sid,[root/'config.json',root/'prepared.json',*[root/n for n in TLS_FILES]]) as data,MutableFile(root/'tls-key.pem',identity.sid) as key_custody,Custody(root/'temp',identity.sid) as temp_custody:
    prepared(root,c,identity.sid,args.expected_package_sha,parent)
    def guard():parent.guard();source.guard();data.guard();key_custody.guard();temp_custody.guard()
    guard()
    if args.action=='preflight':
     need(not (root/'claim.json').exists(),'S0_ALREADY_STARTED')
     if role=='LS5':need(port_available(c['plan']['port']),'S0_PORT_OCCUPIED')
     return dict(status='APPLICATION_PREFLIGHT_PASS_NOT_AUTHORIZATION',**local_context(c),token=dict(elevated=identity.elevated,admin_enabled=identity.admin_enabled,integrity=identity.integrity,enabled_privileges=list(identity.enabled_privileges)),s0_execute=False,g1_execute=False)
    if args.action=='execute':
     if role=='LS5':need(port_available(c['plan']['port']),'S0_PORT_OCCUPIED')
     return execute(args,c,identity,manifest,guard)
    if args.action=='stop':
     with MutableFile(root/'stop.json',identity.sid) as slot:request_stop(root,local_context(c));slot.guard()
     return dict(status='OWN_STOP_NOTIFICATION_WRITTEN_NO_SIGNALS',**local_context(c),g1_execute=False)
    if args.action=='status':
     result=dict(status='S0_NOT_STARTED',**local_context(c),g1_execute=False)
     if (root/'claim.json').exists():
      try:
       with ExclusiveFile(root/'claim.json',identity.sid):result['status']='S0_CLAIM_RELEASED'
      except Exception:result['status']='RUNNING_OR_UNKNOWN'
     if (root/'summary.json').exists():result['summary']=load_json(read_small(root,'summary.json'))
     return result
    if args.action=='evidence':
     from .evidence import archive_evidence
     with ExclusiveFile(root/'claim.json',identity.sid):return archive_evidence(root,local_context(c),args.expected_package_sha)
    raise ValueError('S0_ACTION_BLOCKED')

def main(argv=None):
 try:
  p=Parser(description=__doc__);p.add_argument('--action',choices=('plan','preflight','prepare','execute','status','stop','evidence'),default='plan')
  for name in ('root','package-root','package-zip','config','expected-head','expected-package-sha'):p.add_argument('--'+name)
  p.add_argument('--parent-scope',choices=('LocalAppData','UserProfileV1'),default='LocalAppData');p.add_argument('--approved',action='store_true');args=p.parse_args(argv)
  if args.action=='plan':print(json.dumps(dict(status='PLAN_ONLY',profile='PHYSICAL_SMOKE_S0',command=None,s0_execute=False,g1_execute=False,cleanup=False)));return 0
  if args.action in ('prepare','execute','stop','evidence'):need(args.approved,'S0_EXPLICIT_APPROVAL_REQUIRED')
  need(all(getattr(args,k) for k in ('root','package_root','package_zip','config','expected_head','expected_package_sha')),'S0_PINS_REQUIRED')
  if args.action=='execute':
   from .lifecycle import arm_deadline
   arm_deadline()
  install_guard();result=dispatch(args);print(json.dumps(result,sort_keys=True))
  return 0 if result.get('status') not in ('BLOCKED_OR_PARTIAL','RUNNING_OR_UNKNOWN') else 2
 except Exception as exc:
  print(json.dumps(dict(status='BLOCKED',reason=type(exc).__name__,scope='S0_ONLY',g1_execute=False,cleanup=False)));return 1
