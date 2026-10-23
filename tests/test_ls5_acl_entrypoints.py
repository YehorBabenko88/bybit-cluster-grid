from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('script,first_effect',[
    ('bootstrap.ps1','$InstallRoot='),('bootstrap-ml.ps1','$Req='),
    ('install.ps1','$identity='),('stage-github-release.ps1','$gh = Get-Command'),
    ('protect-service.ps1','Write-Output'),
])
def test_unsafe_preparation_cannot_bypass_acl_proof(script,first_effect):
    s=(ROOT/'installer'/script).read_text(encoding='utf-8')
    assert 'LS5_ACL_EXECUTE_NOT_AUTHORIZED' in s[:s.index(first_effect)]


def test_acl_wrapper_default_has_no_observations_or_writes():
    s=(ROOT/'installer/ls5-acl-remediation.ps1').read_text()
    for forbidden in ('Set-Acl','Get-Acl','icacls','Get-LocalUser','Get-ScheduledTask','New-Item','Start-Process','Invoke-Command'):
        assert forbidden not in s
    assert 'EXECUTE_NOT_AUTHORIZED' in s and 'ROLLBACK_NOT_AUTHORIZED' in s


def test_profile_does_not_use_localized_principals():
    s=(ROOT/'installer/protect-service.ps1').read_text()
    assert 'icacls' not in s and 'sc.exe' not in s
