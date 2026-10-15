"""Synthetic files only; never invokes runtime or PostgreSQL."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LEGACY='9ab1f5b85ec471ea21ec89f1b76740c0b01537b6'
REVIEWED='a'*40
PREVIOUS='b'*40

def make_fixture(root,phase='committed',role='CONTROL',migration=48,legacy=LEGACY):
    root=Path(root)
    for version in (PREVIOUS,REVIEWED,legacy):
        base=root/'releases'/version
        files={'run_coordinator.py':'raise RuntimeError("never execute target")', 'run_worker.py':'raise RuntimeError("never execute target")',
          'grid/coordinator.py':'pass','grid/worker.py':'pass','grid/db.py':'pass','grid/retention.py':'pass'}
        if version==legacy:
            files['grid/migrations.py']=(ROOT/'tests/fixtures/legacy_rollback_migrations.txt').read_text(encoding='utf-8')
        else:
            files.update({'grid/control_runtime.py':'pass','grid/collection_ownership.py':'pass',
              'grid/migrations.py':(ROOT/'grid/migrations.py').read_text(encoding='utf-8')})
        for name,data in files.items():
            p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
        (base/'release-manifest.json').write_text(json.dumps({'version':version,'files':{name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in files}}),encoding='utf-8')
    (root/'current.version').write_text(legacy)
    (root/'previous.version').write_text(PREVIOUS)
    (root/'pending.version').write_text(legacy)
    if phase!='none':
        (root/'switch-journal.json').write_text(json.dumps({'schema':1,'phase':phase,'previous':PREVIOUS,'candidate':legacy}))
    evidence={'schema':1,'mode':'read-only','activation_authorized':False,'database_checked':True,'status':'PASS',
        'checks':{'release':{'status':'PASS','code':'RELEASE_VERIFIED','version':REVIEWED},
          'database':{'status':'PASS','code':'DATABASE_READY','migration':migration,'runtime_state':'STOPPED'}}}
    (root/'schema-evidence.json').write_text(json.dumps(evidence),encoding='utf-8')
    return root

if __name__=='__main__':
    make_fixture(sys.argv[1],sys.argv[2],sys.argv[3])
