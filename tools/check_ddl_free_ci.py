"""Exact-commit receipts and zero-skip CI gate; no physical commissioning."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import pytest

ROOT=Path(__file__).resolve().parents[1]


def verify_checkout(root, sha):
    """Receipt covers the executed tracked checkout, not merely Git objects.

    Git performs checkout newline normalization. Untracked runtime Python is
    forbidden too; ignored test artifacts and bytecode are not executable inputs.
    """
    actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
    if actual != sha:
        raise RuntimeError('CHECKOUT_HEAD_MISMATCH')
    status = subprocess.run(['git','diff','--quiet','HEAD','--'],cwd=root)
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root).decode().splitlines()
    if status.returncode != 0 or any(Path(p).suffix.lower() in ('.py','.ps1','.sql','.pyd','.dll') for p in untracked):
        raise RuntimeError('CHECKOUT_DIRTY')
    # git diff alone trusts assume-unchanged/skip-worktree index flags. Compare
    # actual regular-file bytes to HEAD objects independently of those flags.
    entries = []
    for record in subprocess.check_output(['git','ls-tree','-rz','--full-tree','HEAD'],cwd=root).split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t',1)
        mode, kind, oid = metadata.split()
        if mode not in (b'100644',b'100755') or kind != b'blob':
            raise RuntimeError('CHECKOUT_UNSUPPORTED_FILE_KIND')
        entries.append((name.decode('utf-8'),oid))
    objects = io.BytesIO(subprocess.check_output(['git','cat-file','--batch'],cwd=root,
                         input=b''.join(oid+b'\n' for _,oid in entries)))
    for name, oid in entries:
        header = objects.readline().split()
        if len(header)!=3 or header[:2]!=[oid,b'blob']:
            raise RuntimeError('CHECKOUT_OBJECT_MISMATCH')
        expected = objects.read(int(header[2]))
        if objects.read(1)!=b'\n':
            raise RuntimeError('CHECKOUT_OBJECT_MISMATCH')
        path = root/name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('CHECKOUT_DIRTY')
        actual = path.read_bytes()
        if expected == actual:
            continue
        try:
            expected.decode('utf-8'); actual.decode('utf-8')
        except UnicodeError:
            raise RuntimeError('CHECKOUT_DIRTY') from None
        if b'\0' in expected or b'\0' in actual or expected.replace(b'\r\n',b'\n')!=actual.replace(b'\r\n',b'\n'):
            raise RuntimeError('CHECKOUT_DIRTY')


def changed_source_receipt(root,baseline,head):
    names=subprocess.check_output(['git','diff','--name-only','-z',baseline,head],cwd=root).decode().split('\0')
    current=set(subprocess.check_output(['git','ls-tree','-r','--name-only','-z',head],cwd=root).decode().split('\0'))
    files={};deleted=[]
    for name in filter(None,names):
        if name not in current:deleted.append(name)
        else:files[name]=hashlib.sha256(subprocess.check_output(['git','show',head+':'+name],cwd=root)).hexdigest()
    return files,sorted(deleted)


class Receipt:
    def __init__(self):
        self.nodes=[]; self.passed=[]; self.bad=[]

    @pytest.fixture(autouse=True)
    def isolated_paths(self,monkeypatch,tmp_path):
        monkeypatch.setenv('ProgramData',str(tmp_path/'programdata'))
        monkeypatch.setenv('PROGRAMDATA',str(tmp_path/'programdata'))

    def pytest_collection_finish(self,session):
        self.nodes=sorted(x.nodeid for x in session.items)

    def pytest_runtest_logreport(self,report):
        if hasattr(report,'wasxfail') or report.outcome!='passed':
            self.bad.append([report.nodeid,report.when,report.outcome])
        if report.when=='call' and report.outcome=='passed':
            self.passed.append(report.nodeid)


def run(mode):
    verify_checkout(ROOT, os.environ['EXACT_HEAD_SHA'])
    # Establish sandbox BEFORE test collection imports Worker/config/resources.
    if (ROOT/'.env').exists():
        raise RuntimeError('TEST_CHECKOUT_MUST_NOT_CONTAIN_DOTENV')
    os.environ['NODE_ID']='synthetic-ci-node'
    sandbox=Path(tempfile.mkdtemp(prefix='grid-ddl-test-'))
    os.environ['ProgramData']=os.environ['PROGRAMDATA']=str(sandbox)
    if mode=='offline':
        for key in ('POSTGRES_DSN','GRID_DISPOSABLE_POSTGRES_TESTS','GRID_PG18_TESTS'):
            os.environ.pop(key,None)
    inv=json.loads((ROOT/'tests/fixtures'/f'ddl_{mode}_inventory.json').read_text())
    receipt=Receipt()
    prefix='ddl-'+mode
    code=pytest.main(['-q','-p','no:cacheprovider','--basetemp',str(sandbox/'pytest'),
                     *inv['nodes'],'--junitxml',prefix+'.xml'],plugins=[receipt])
    events={'sha':os.environ['EXACT_HEAD_SHA'],
            'run_id':os.environ['GITHUB_RUN_ID'], 'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'collected':receipt.nodes,
            'passed':sorted(receipt.passed),'bad':receipt.bad}
    Path(prefix+'-events.json').write_text(json.dumps(events,sort_keys=True),encoding='utf-8')
    assert code==0 and not receipt.bad
    assert receipt.nodes==inv['nodes']==sorted(receipt.passed)
    tree=ET.parse(prefix+'.xml')
    cases=list(tree.iter('testcase'))
    assert len(cases)==len(inv['nodes'])
    assert sorted([c.get('classname'),c.get('name')] for c in cases)==inv['junit_cases']
    assert all(int(s.get(k,0))==0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
    verify_checkout(ROOT, os.environ['EXACT_HEAD_SHA'])
    files,deleted=changed_source_receipt(ROOT,'f99f401aa11b5f0e0ed75046960801f882540216','HEAD')
    for name in (prefix+'.xml',prefix+'-events.json',
                 *[n for n in ('ddl-dependencies.txt','pg18-provider.json') if Path(n).exists()]):
        files[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    Path(prefix+'-sha256.json').write_text(json.dumps({'sha':events['sha'],'run_id':events['run_id'],'run_attempt':events['run_attempt'],'files':files,'deleted_paths':deleted},indent=2),encoding='utf-8')


if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==os.environ['EXACT_HEAD_SHA']
    assert len(sys.argv)==2 and sys.argv[1] in ('offline','pg18')
    run(sys.argv[1])
