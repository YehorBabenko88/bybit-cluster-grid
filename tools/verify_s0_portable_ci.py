"""Owned hosted fixture only: execute portable Plan/import checks, never S0 physical Execute."""
import hashlib,json,os,subprocess,sys,uuid,zipfile
from pathlib import Path
from tools.build_s0_package import require_hosted,hosted_local_app_data,hosted_native_build_root,create_hosted_root
from tools.check_ddl_free_ci import ROOT,verify_checkout
from s0_smoke.package import verify_package,name
from tools.s0_native_receipt import validate_native
from s0_smoke.windows import current_identity,create_fresh_root,Custody

def run():
 import socket
 require_hosted(os.environ,socket.gethostname());head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
 receipt=json.loads((ROOT/'s0-package/package-receipt.json').read_text());archive=ROOT/'s0-package'/receipt['package'];raw=archive.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=receipt['sha256'] or receipt['head']!=head:raise RuntimeError('S0_PACKAGE_RECEIPT_MISMATCH')
 identity=current_identity();fixture=hosted_local_app_data()/('s0-portable-'+str(uuid.uuid4()));create_hosted_root(fixture,identity.sid)
 with zipfile.ZipFile(archive) as z:
  for info in z.infolist():
   name(info.filename)
   if info.is_dir() or info.file_size>67108864:raise RuntimeError('S0_MEMBER_BLOCKED')
   target=fixture/info.filename;target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('xb') as f:f.write(z.read(info.filename))
 with (fixture/'source.zip').open('xb') as f:f.write(raw)
 (fixture/'temp').mkdir();manifest=verify_package(fixture,fixture/'source.zip',head,receipt['sha256'])
 files=[fixture/n for n in manifest['files']]+[fixture/'s0-package.json',fixture/'source.zip'];runs=[]
 env={k:os.environ[k] for k in ('SystemRoot','WINDIR','USERPROFILE','LOCALAPPDATA','USERNAME','COMPUTERNAME') if k in os.environ};env.update(TEMP=str(fixture/'temp'),TMP=str(fixture/'temp'),PATH=str(Path(os.environ['SystemRoot'])/'System32'))
 with Custody(fixture,identity.sid,files) as custody:
  exe=str(fixture/'runtime/python.exe');entry=str(fixture/'runtime/App/s0.py')
  commands=[([exe,'-I','-S','-B',entry,'--action','plan'],0),([exe,'-I','-S','-B',entry,'--action','execute'],1),([exe,'-I','-S','-B','-c',"import aiohttp,cryptography,importlib.util,json,sys; print(json.dumps(dict(aiohttp=aiohttp.__version__,cryptography=cryptography.__version__,isolated=sys.flags.isolated,no_site=sys.flags.no_site,grid_absent=importlib.util.find_spec('grid') is None)))"],0)]
  for argv,expected in commands:
   custody.guard()
   with subprocess.Popen(argv,cwd=fixture,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
    out,err=child.communicate(timeout=15);code=child.returncode;pid=child.pid
   (ROOT/'s0-results'/('portable-raw-'+str(len(runs))+'.json')).write_text(json.dumps(dict(exit_code=code,stdout=out.decode('utf-8','replace')[:16000],stderr=err.decode('utf-8','replace')[:16000])))
   if code!=expected or err:raise RuntimeError('S0_PORTABLE_CHILD_FAILED')
   value=json.loads(out)
   if len(runs)==0 and not(value.get('status')=='PLAN_ONLY' and value.get('command') is None and value.get('g1_execute') is False):raise RuntimeError('S0_PLAN_FALSE_AUTHORITY')
   if len(runs)==1 and value.get('status')!='BLOCKED':raise RuntimeError('S0_UNAPPROVED_EXECUTE_NOT_BLOCKED')
   if len(runs)==2 and value!=dict(aiohttp='3.14.5',cryptography='50.0.2',isolated=1,no_site=1,grid_absent=True):raise RuntimeError('S0_PORTABLE_CLOSURE_MISMATCH')
   runs.append(dict(pid=pid,exit_code=code,result=value,scope='OWNED_HOSTED_PLAN_OR_IMPORT_ONLY'));custody.guard()
 native_build=hosted_native_build_root();native_files=[native_build/'Fixture.exe',native_build/'S0Launcher.dll']
 with Custody(native_build,identity.sid,native_files) as native_custody,Custody(fixture,identity.sid,files) as child_source:
  if hashlib.sha256((native_build/'S0Launcher.dll').read_bytes()).hexdigest()!=manifest['files']['native/S0Launcher.dll']['sha256']:raise RuntimeError('S0_NATIVE_DLL_MISMATCH')
  ci_env=dict(env)
  for key in ('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_REPOSITORY','GITHUB_JOB','EXACT_HEAD_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','RUNNER_TEMP'):ci_env[key]=os.environ[key]
  with subprocess.Popen([str(native_build/'Fixture.exe'),'--parent',str(fixture),manifest['files']['runtime/python.exe']['sha256'],head,str(fixture/'temp/native-launcher.json')],cwd=native_build,env=ci_env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
   native_out,native_err=child.communicate(timeout=100);native_exit=child.returncode
  native_custody.guard()
  (ROOT/'s0-results/native-launcher-raw.txt').write_bytes(native_out[:65536])
  if native_exit!=0 or native_err:raise RuntimeError('S0_NATIVE_FIXTURE_FAILED')
  native_record=validate_native(json.loads(native_out),head,identity.sid)
  if not(native_record.get('head')==head and native_record.get('scope')=='HOSTED_FIXTURE_NOT_PHYSICAL' and native_record.get('wrong_hash_rejected') is True and native_record.get('wrong_sid_rejected') is True):raise RuntimeError('S0_NATIVE_RECORD_BLOCKED')
  for label in ('normal','deadline','descendant_denied'):
   record=native_record[label]
   if not(record['observed_elevated'] is False and record['observed_admin_enabled'] is False and record['observed_integrity']=='S-1-16-8192' and record['job_member'] is True and record['job_flags']==0x2008 and record['active_limit']==1):raise RuntimeError('S0_NATIVE_TOKEN_OR_JOB_BLOCKED')
  native_record.update(run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],binary_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in native_files},source_sha256={n:hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest() for n in ('installer/physical-smoke-s0/S0Launcher.cs','installer/physical-smoke-s0-tests/Fixture.cs')})
  (ROOT/'s0-results/native-launcher.json').write_text(json.dumps(native_record,indent=2))
 output=dict(head=head,tree=receipt['tree'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],package_sha256=receipt['sha256'],status='PORTABLE_PLAN_AND_IMPORTS_PASS',runs=runs,s0_execute=False,g1_execute=False,physical='NOT_RUN')
 (ROOT/'s0-results/portable.json').write_text(json.dumps(output,indent=2));verify_checkout(ROOT,head);print(json.dumps(output))

if __name__=='__main__':run()
