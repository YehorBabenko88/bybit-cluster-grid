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

def test_every_externally_pinned_grid_sdk_input_disables_text_conversion():
    import subprocess
    paths=['installer/PortableRuntime.psm1','installer/NativeJobProcess.cs',
           'installer/PinnedVendorDownload.psm1','installer/pinned-vendor-download.tests.ps1']
    fields=subprocess.check_output(['git','check-attr','-z','text','--',*paths]).split(b'\0')
    assert fields[-1]==b''
    actual={fields[i].decode():fields[i+2].decode() for i in range(0,len(fields)-1,3)}
    assert actual==dict.fromkeys(paths,'unset')


def test_reviewed_fixed_root_checkout_and_source_hashes_are_coherent():
    job=yaml.safe_load(Path('.github/workflows/portable-sdk-qualification.yml').read_text())['jobs']['component-sdk']
    expected={
        'UNIFIED_SHA':'21b8861e93f3bbe93480aec8011758ae66b40d7d',
        'UNIFIED_TREE':'dce0f1f998b23cd3011d1f363d8b5f73bca3dfc4',
        'GUARD_SHA256':'8236203c76f8b28a4b426ca9ece4a2bb56bd0dd1a02375e02418d859e3f82a37',
        'PREFLIGHT_SHA256':'b4273a187653c7447f66a60fb9898dadab0a752a1745b0f771dcb1e5aad8a221',
        'CATALOG_SHA256':'8f03e40a411033532a9a349025db9c6299a2cb52da16b8a839e7d4912bc5041b',
    }
    assert {key:job['env'][key] for key in expected}==expected
    checkout=next(step for step in job['steps'] if step.get('with',{}).get('repository')=='YehorBabenko88/unified-system')
    assert checkout['with']['ref']==expected['UNIFIED_SHA']
