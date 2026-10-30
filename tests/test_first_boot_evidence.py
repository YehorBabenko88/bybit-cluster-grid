import json
import pytest


def test_e2e_summary_never_accepts_blocked_or_physical_promotion():
    from integration.verify_first_boot_evidence import verify_summary
    from integration.first_boot_evidence import REQUIRED
    base=dict(schema=1,head='a'*40,run_id='1',attempt='1',core_status='ISOLATED_E2E_PASS',whole_system='PARTIAL',
              required=list(REQUIRED),missing=[],error_class=None,physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')
    verify_summary(base,'a'*40,'1','1')
    for key,value in [('physical','PASS'),('execute','AUTHORIZED'),('core_status','BLOCKED'),('missing',['schema-preparation']),('head','b'*40),('error_class','TimeoutError')]:
        with pytest.raises(ValueError):verify_summary(dict(base,**{key:value}),'a'*40,'1','1')


def test_owned_evidence_path_cannot_escape_or_follow_symlink(tmp_path):
    from integration.verify_first_boot_evidence import owned_file
    with pytest.raises(ValueError):owned_file(tmp_path,'../outside')
    with pytest.raises(ValueError):owned_file(tmp_path,'C:/Windows/secret')
