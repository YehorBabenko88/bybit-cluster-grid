"""GitHub runner schema regression for the mandatory PowerShell matrix."""
from pathlib import Path
import yaml


def test_transport_matrix_uses_supported_literal_shells_and_reports_selected_cell():
    workflow=yaml.safe_load(Path('.github/workflows/portable-sdk-qualification.yml').read_text())
    job=workflow['jobs']['component-sdk']
    assert set(job['strategy']['matrix']['engine'])=={'powershell','pwsh'}
    steps=job['steps']
    for step in steps:
        assert '${{ matrix.' not in step.get('shell',''), 'GitHub rejects matrix context in shell'
    indexed={step['id']:step for step in steps if 'id' in step}
    for engine in ('powershell','pwsh'):
        step=indexed['transport_tests_'+engine]
        assert step['shell']==engine
        assert step['if']=="matrix.engine == '"+engine+"'"
        assert 'DOWNLOAD_HELPER_SHA256' in step['run']
        assert 'DOWNLOAD_TEST_SHA256' in step['run']
        assert 'Save-PinnedNssmMirrorPackage' in step['run']
        assert '& $tests -PackageFile $fixture' in step['run']
    report=next(step for step in steps if step.get('name')=='Record exact source and actual outcomes')
    assert report['env']['TRANSPORT_TEST_OUTCOME']=="${{ matrix.engine == 'powershell' && steps.transport_tests_powershell.outcome || steps.transport_tests_pwsh.outcome }}"


def test_source_hash_pins_match_canonical_raw_git_blobs_after_materialization():
    import hashlib
    import subprocess
    workflow=yaml.safe_load(Path('.github/workflows/portable-sdk-qualification.yml').read_text())
    pins=workflow['jobs']['component-sdk']['env']
    for filename,key in (
        ('installer/PortableRuntime.psm1','LIBRARY_SHA256'),
        ('installer/NativeJobProcess.cs','NATIVE_JOB_SHA256'),
        ('installer/PinnedVendorDownload.psm1','DOWNLOAD_HELPER_SHA256'),
        ('installer/pinned-vendor-download.tests.ps1','DOWNLOAD_TEST_SHA256'),
    ):
        # CI checkout-index with autocrlf=false materializes these raw Git bytes.
        # A Windows working tree may still have CRLF or mixed line endings.
        raw=subprocess.check_output(['git','show','HEAD:'+filename])
        assert hashlib.sha256(raw).hexdigest()==pins[key],key
