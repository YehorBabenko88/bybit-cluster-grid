"""Development-only: list the repository paths the 18 original nodes read (audit hook).

Usage: python trace_original_reads.py <strattester@3850995 checkout> <out.json> <node-id-list>
Directories, __pycache__ and .pyc entries are filtered by the caller before building the ledger."""
import sys, os, pytest, json
root=os.path.realpath(sys.argv[1]); out=sys.argv[2]; ids=open(sys.argv[3]).read().split()
seen=set()
def hook(ev,args):
    if ev=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p=os.path.realpath(os.fsdecode(args[0]))
        if p.startswith(root+'/'): seen.add(os.path.relpath(p,root))
    if ev=='os.scandir' or ev=='os.listdir':
        try:
            p=os.path.realpath(os.fsdecode(args[0]));
            if p.startswith(root): seen.add('DIR:'+os.path.relpath(p,root))
        except Exception: pass
sys.addaudithook(hook)
os.chdir(root)
rc=pytest.main(['-q','-p','no:cacheprovider',*ids])
json.dump(sorted(seen),open(out,'w'),indent=1)
print('rc',rc)
