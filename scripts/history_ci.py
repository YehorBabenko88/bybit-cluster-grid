"""Exact-head research receipt; never source authenticity proof."""
import hashlib,io,json,os,subprocess,sys,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def git(*a):return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*a],timeout=30)
def gt(*a):return git(*a).decode().strip()
def sha(b):return hashlib.sha256(b).hexdigest()
TEXT={'.py','.mjs','.json','.yml','.yaml','.toml','.html','.css','.md','.txt','.ps1','.sh'}
def snapshot():
 head=gt('rev-parse','HEAD')
 if head!=os.environ.get('EXPECTED_SOURCE_SHA',head) or gt('status','--porcelain','--untracked-files=no'):raise ValueError('EXACT_HEAD_OR_DIRTY_SOURCE')
 sources={};archive=git('archive',head)
 if len(archive)>64*1024*1024:raise ValueError('SOURCE_LIMIT')
 with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
  for member in tar:
   path=Path(member.name)
   if member.isdir() or path.suffix not in TEXT|{'.sql'}:continue
   tested_path=root/member.name
   if not member.isfile() or tested_path.is_symlink():raise ValueError('SOURCE_LINK')
   committed=tar.extractfile(member).read();tested=tested_path.read_bytes()
   def normalized(b):return b.replace(b'\r\n',b'\n') if path.suffix in TEXT else b
   if normalized(committed)!=normalized(tested):raise ValueError('SOURCE_BYTES')
   sources[member.name]={'git_blob_sha256':sha(committed),'tested_file_sha256':sha(tested)}
 return head,gt('rev-parse','HEAD^{tree}'),sources
def main():
 out=root/'.history-evidence';out.mkdir(exist_ok=True)
 try:
  head,tree,sources=snapshot()
  command=[sys.executable,'-m','unittest','discover','-s',sys.argv[1],'-p',sys.argv[2],'-v']
  r=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=480)
  (out/'tests.log').write_bytes(r.stdout)
  unchanged=snapshot()==(head,tree,sources);code=r.returncode if unchanged else 1
  receipt={'schema':'history.ci.receipt.v1','head':head,'tree':tree,'parents':gt('show','-s','--format=%P','HEAD'),
   'run_id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'job':os.environ.get('GITHUB_JOB'),
   'command':command,'test_exit_code':code,'source_binding':'COMMITTED_TEXT_LF_EQUIVALENT_SQL_RAW_BYTES',
   'tested_source_unchanged':unchanged,'python_sha256':sha(Path(sys.executable).read_bytes()),
   'log_sha256':sha(r.stdout),'sources':sources,'evidence_class':'SYNTHETIC','source_authenticity':'BLOCKED','trading_authorized':False}
  data=json.dumps(receipt,indent=2,sort_keys=True).encode();(out/'receipt.json').write_bytes(data)
  (out/'SHA256SUMS').write_text(sha(data)+'  receipt.json\n'+sha(r.stdout)+'  tests.log\n')
  print(r.stdout.decode(errors='replace'));print(json.dumps({'head':head,'tree':tree,'test_exit_code':code,'receipt_sha256':sha(data)}))
  return code
 except (ValueError,OSError,subprocess.SubprocessError):
  print('EXACT_HEAD_QUALIFICATION_BLOCKED',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
