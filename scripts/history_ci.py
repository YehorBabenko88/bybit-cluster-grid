"""Exact-head research receipt; never source authenticity proof."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def git(*a):return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*a],timeout=30)
def gt(*a):return git(*a).decode().strip()
def sha(b):return hashlib.sha256(b).hexdigest()
TEXT={'.py','.mjs','.json','.yml','.yaml','.toml','.html','.css','.md','.txt','.ps1','.sh'}
def snapshot():
 head=gt('rev-parse','HEAD')
 if head!=os.environ.get('EXPECTED_SOURCE_SHA',head) or gt('status','--porcelain','--untracked-files=no'):raise ValueError('EXACT_HEAD_OR_DIRTY_SOURCE')
 sources={};entries=[]
 for line in git('ls-tree','-r','-z','-l',head).split(b'\0'):
  if not line:continue
  metadata,name=line.split(b'\t',1);mode,kind,oid,size=metadata.split()
  path=name.decode()
  if Path(path).suffix not in TEXT|{'.sql'}:continue
  if mode not in (b'100644',b'100755') or kind!=b'blob':raise ValueError('SOURCE_MODE')
  entries.append((path,oid,int(size)))
 if sum(size for _,_,size in entries)>64*1024*1024:raise ValueError('SOURCE_LIMIT')
 batch=subprocess.check_output(['git','--no-replace-objects','-C',str(root),'cat-file','--batch'],
  input=b''.join(oid+b'\n' for _,oid,_ in entries),timeout=30)
 offset=0
 for path,oid,size in entries:
  end=batch.index(b'\n',offset);actual_oid,kind,actual_size=batch[offset:end].split()
  if actual_oid!=oid or kind!=b'blob' or int(actual_size)!=size:raise ValueError('BLOB_HEADER')
  committed=batch[end+1:end+1+size];offset=end+size+2
  tested_path=root/path
  if tested_path.is_symlink():raise ValueError('SOURCE_LINK')
  tested=tested_path.read_bytes()
  def normalized(b):return b.replace(b'\r\n',b'\n') if Path(path).suffix in TEXT else b
  if normalized(committed)!=normalized(tested):raise ValueError('SOURCE_BYTES')
  sources[path]={'git_blob_sha256':sha(committed),'tested_file_sha256':sha(tested)}
 if offset!=len(batch):raise ValueError('BLOB_TRAILING_BYTES')
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
