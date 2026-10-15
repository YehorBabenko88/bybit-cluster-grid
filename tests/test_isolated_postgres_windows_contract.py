"""Cross-language contract; only the explicitly mocked collector fixture is executed."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from installer.isolated_postgres_preflight import assess
from test_isolated_postgres_plan import example
from test_isolated_postgres_preflight import adapter, SID, SHA

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows collector contract runs in Windows CI matrix')

@pytest.mark.parametrize('shell',['powershell.exe','pwsh'])
def test_real_ps_serialization_roundtrips_without_host_probes(shell):
    executable=shutil.which(shell)
    assert executable, 'Required Windows PowerShell engine missing'
    plan=example()
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    fixture=Path(__file__).resolve().parents[1]/'installer/tests/test-isolated-postgres-readonly.ps1'
    child=subprocess.run([executable,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(fixture),
                          '-EmitSnapshot','-EvidencePlanHash',digest],check=True,capture_output=True,text=True)
    e=json.loads(child.stdout)
    r=assess(plan,SHA,mode='PreflightReadOnly',evidence=e,adapter_plan=adapter(),
             expected_owner_sid=SID,now=dt.datetime.now(dt.timezone.utc))
    assert r['checks']['host_evidence']=='METADATA_ONLY',r
    assert 'ADAPTER_LAYOUT_INCOMPATIBLE' in r['blockers']
    assert r['execution_authorized'] is False and r['physical_ready'] is False
