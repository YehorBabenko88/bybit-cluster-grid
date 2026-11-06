"""Negative source-proof probes in a separate owned .git clone only.

No product tests or consensus claims. Never writes refs in source/linked repos.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import types


def probe(expected, scratch):
    source=Path(__file__).resolve().parents[3]
    scratch=Path(scratch).resolve();scratch.mkdir(parents=True,exist_ok=False)
    clone=scratch/'owned-clone'
    env=os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_COUNT='0',PYTHONDONTWRITEBYTECODE='1')
    def git(*args,input=None):
        return subprocess.check_output(['git','--no-replace-objects',*args],cwd=clone,env=env,input=input)
    subprocess.run(['git','--no-replace-objects','-c','core.autocrlf=false','-c','core.eol=lf',
        'clone','--no-hardlinks','--no-checkout',str(source),str(clone)],env=env,check=True)
    git('-c','core.autocrlf=false','-c','core.eol=lf','checkout','--detach',expected)
    # A real independent object database, never a linked worktree's shared refs.
    assert (clone/'.git').is_dir() and not (clone/'.git').is_symlink()
    gd=git('rev-parse','--git-dir').strip();gc=git('rev-parse','--git-common-dir').strip()
    assert gd==gc==b'.git'
    verify=runpy.run_path(str(clone/'lab/consul/source_receipt.py'))['verify']
    calls=[]
    def recorded(command,**kwargs):
        assert command[:2]==['git','--no-replace-objects'], 'EXPLICIT_NO_REPLACE_REQUIRED'
        calls.append(command)
        return subprocess.check_output(command,**kwargs)
    verify.__globals__['subprocess']=types.SimpleNamespace(check_output=recorded)
    previous=Path.cwd();cases=[]
    try:
        os.chdir(clone)
        baseline=verify(expected)
        assert baseline['head']==expected
        cases.append(dict(case='CLEAN_RAW_HEAD_BASELINE',result='PASS'))
        path=clone/'grid/coordination_event_v3.py';raw=path.read_bytes()
        original_blob=git('rev-parse',expected+':grid/coordination_event_v3.py').decode().strip()
        changed=raw+b'\n# owned isolated negative source-proof probe\n'
        replacement=git('hash-object','-w','--stdin',input=changed).decode().strip()
        path.write_bytes(changed)
        git('replace',original_blob,replacement)
        try:
            try:verify(expected)
            except ValueError as exc:
                assert 'SOURCE_RAW_BLOB_MISMATCH' in str(exc)
                cases.append(dict(case='BLOB_REPLACEMENT_REJECTED_BEFORE_TESTS',result='REJECTED',reason=str(exc)))
            else:raise AssertionError('BLOB_REPLACE_MUST_NOT_BIND_MODIFIED_SOURCE')
        finally:
            git('replace','-d',original_blob);path.write_bytes(raw)
        tree=git('rev-parse',expected+'^{tree}').decode().strip()
        git('add','--','grid/coordination_event_v3.py')
        # Build a distinct replacement tree using the same harmless source change.
        path.write_bytes(changed);git('add','--','grid/coordination_event_v3.py')
        replacement_tree=git('write-tree').decode().strip()
        git('replace',tree,replacement_tree)
        try:
            try:verify(expected)
            except ValueError as exc:
                assert 'SOURCE_RAW_BLOB_MISMATCH' in str(exc)
                cases.append(dict(case='TREE_REPLACEMENT_REJECTED_BEFORE_TESTS',result='REJECTED',reason=str(exc)))
            else:raise AssertionError('TREE_REPLACE_MUST_NOT_BIND_MODIFIED_SOURCE')
        finally:
            git('replace','-d',tree);path.write_bytes(raw);git('reset','--mixed',expected)
        assert verify(expected)['tree']==baseline['tree']
        assert not git('for-each-ref','refs/replace').strip()
        cases.append(dict(case='RESTORED_RAW_HEAD_BASELINE',result='PASS'))
        report=dict(schema='grid.event-v3.no-replace-proof.v1',head=expected,tree=baseline['tree'],
            cases=cases,guard_git_calls=len(calls),all_explicit_no_replace=True,
            scope='SOURCE_PROOF_ONLY_NO_PRODUCT_TEST_OR_AUTHORITY_PASS',
            source_repo_refs_changed=False,negative_refs_location=str(clone/'.git'),
            product_source_sha256=hashlib.sha256(raw).hexdigest())
        (scratch/'evidence.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
        print(json.dumps(dict(cases=len(cases),result='NO_REPLACE_PROBES_MATCH',head=expected)))
    finally:
        os.chdir(previous)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected',required=True);parser.add_argument('--scratch',required=True)
    args=parser.parse_args();probe(args.expected,args.scratch)
