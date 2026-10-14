"""Test-only subprocess harness. No network or application runtime is invoked."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from installer import windows_preflight as w
from grid.migrations import MIGRATIONS

if sys.argv[1] == '--make-fixture':
    root=Path(sys.argv[2]);sha=sys.argv[3];root.mkdir(parents=True,exist_ok=True)
    files={'run_coordinator.py':'# fixture','run_worker.py':'# fixture','grid/coordinator.py':'# fixture',
           'grid/worker.py':'# fixture','grid/db.py':'# fixture','grid/retention.py':'# fixture',
           'grid/migrations.py':(Path(__file__).resolve().parents[2]/'tests/fixtures/legacy_rollback_migrations.txt').read_text()}
    for n,data in files.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
    (root/'release-manifest.json').write_text(json.dumps({'version':sha,'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}}))
    sys.exit(0)

class Evidence:
    def transaction(self,**kwargs):
        if kwargs != {'readonly':True}:raise AssertionError('read-only transaction required')
        @asynccontextmanager
        async def tx():yield
        return tx()
    async def fetchval(self,sql,*args):
        if 'current_database' in sql:return 'bybit_cluster_grid'
        if 'to_regclass' in sql:return args[0]
        if 'state FROM grid_runtime_state' in sql:return 'STOPPED'
        if 'EXISTS' in sql:return False
        raise AssertionError('unexpected SQL')
    async def fetch(self,sql,*args):
        if 'information_schema' in sql:
            return [{'table_name':t,'column_name':n,'udt_name':k} for (t,n),k in w.COLUMNS.items()]
        catalogue=MIGRATIONS[:34] if os.environ.get('GRID_SYNTHETIC_EVIDENCE')=='old-schema' else MIGRATIONS
        return [{'version':v,'name':n} for v,n,_ in catalogue]

async def fake_probe(dsn,**kwargs):
    if dsn != 'postgresql://fixture/bybit_cluster_grid':raise AssertionError('fixture DSN required')
    return await w.database_status(Evidence(),'bybit_cluster_grid',**kwargs)
w.probe_database=fake_probe
w.check_dependencies=lambda:{'status':'PASS','code':'TEST_DEPENDENCY_SUBPROCESS_OMITTED'}
for key in ('TELEGRAM_BOT_TOKEN','BYBIT_API_KEY','BYBIT_API_SECRET'):os.environ.pop(key,None)
sys.exit(w.main(sys.argv[1:]))
