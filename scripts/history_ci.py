"""Exact-head synthetic CI receipt, never source authenticity proof."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def git(*a):return subprocess.check_output(['git','-C',str(root),*a]).decode().strip()
command=[sys.executable,'-m','unittest','discover','-s',sys.argv[1],'-p',sys.argv[2],'-v']
r=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
out=root/'.history-evidence';out.mkdir(exist_ok=True)
(out/'tests.log').write_bytes(r.stdout)
sources={}
for f in git('ls-files').splitlines():
 if ('history' in f and f.endswith(('.py','.json','.md','.yml'))) or f.startswith('python/'):
  b=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+f])
  sources[f]={'git_blob_sha256':hashlib.sha256(b).hexdigest(),'tested_file_sha256':hashlib.sha256((root/f).read_bytes()).hexdigest()}
receipt={'schema':'history.ci.receipt.v1','head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
 'parents':git('show','-s','--format=%P','HEAD'),'run_id':os.environ.get('GITHUB_RUN_ID'),
 'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'job':os.environ.get('GITHUB_JOB'),'command':command,
 'test_exit_code':r.returncode,'log_sha256':hashlib.sha256(r.stdout).hexdigest(),'sources':sources,
 'evidence_class':'SYNTHETIC','source_authenticity':'BLOCKED','trading_authorized':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True),encoding='utf8')
print(r.stdout.decode(errors='replace'));print(json.dumps(receipt,sort_keys=True))
sys.exit(r.returncode)
