"""Fail-closed JUnit accounting for disposable native adversarial CI evidence."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as E

EXPECTED=frozenset([
 'test_real_junction_before_session','test_real_junction_while_pinned',
 'test_real_pinned_ancestor_rename[]','test_real_pinned_ancestor_rename[data]',
 'test_real_pinned_ancestor_rename[postgres]','test_real_protected_acl_change_mid_callback',
 'test_real_acl_replace_restore_aba_limit','test_real_hardlink_race_mid_callback',
 'test_real_concurrent_namespace_mutation','test_bounded_kernel_exhaustion_unproven',
 'test_cleanup_fault_injection_over_real_handles[close]',
 'test_cleanup_fault_injection_over_real_handles[release]',
 'test_real_abandoned_fixture_mutex','test_real_expired_view_cannot_poison_next_session',
 'test_real_acquisition_registration_abort[file]',
 'test_real_acquisition_registration_abort[mutex-dict]',
 'test_real_acquisition_registration_abort[mutex-stack]',
])
ALLOWED_UNPROVEN=frozenset(['test_real_junction_before_session',
                          'test_real_junction_while_pinned','test_bounded_kernel_exhaustion_unproven'])


OBSERVATIONS={
 'test_real_junction_before_session':{'JUNCTION_CREATED_SESSION_BLOCKED'},
 'test_real_junction_while_pinned':{'JUNCTION_DENIED_SYNTHETIC_ONLY','JUNCTION_CREATED_SYNTHETIC_ONLY'},
 'test_real_protected_acl_change_mid_callback':{'FOREIGN_GENERIC_WRITE_ACL_BLOCKED'},
 'test_real_acl_replace_restore_aba_limit':{'ACL_ABA_UNDETECTED_LIMIT','ACL_ABA_DETECTED_THIS_RUN'},
 'test_real_hardlink_race_mid_callback':{'HARDLINK_CREATED_SYNTHETIC_ONLY','HARDLINK_DENIED_SYNTHETIC_ONLY'},
 'test_real_concurrent_namespace_mutation':{'CONCURRENT_NAMESPACE_BLOCKED'},
 'test_bounded_kernel_exhaustion_unproven':{'BOUNDED_FOUR_REAL_HANDLES_QUOTA_BLOCKED'},
 'test_cleanup_fault_injection_over_real_handles[close]':{'INJECTED_CLOSE_REAL_RESOURCES_DRAINED'},
 'test_cleanup_fault_injection_over_real_handles[release]':{'INJECTED_RELEASE_REAL_RESOURCES_DRAINED'},
 'test_real_abandoned_fixture_mutex':{'REAL_ABANDONED_MUTEX_BLOCKED_AND_RELEASED'},
 'test_real_expired_view_cannot_poison_next_session':{'EXPIRED_VIEW_ISOLATED_FROM_NEW_SESSION'},
}
for _name in EXPECTED:
    if _name.startswith('test_real_pinned_ancestor_rename'):
        OBSERVATIONS[_name]={'ANCESTOR_DENIED_SYNTHETIC_ONLY','ANCESTOR_RENAMED_SYNTHETIC_ONLY'}
    if _name.startswith('test_real_acquisition_registration_abort'):
        OBSERVATIONS[_name]={'REGISTRATION_ABORT_RAW_RESOURCE_CLOSED'}


def assess(root,commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('COMMIT_INVALID')
    cases=list(root.iter('testcase'))
    names=[t.get('name') for t in cases]
    if len(cases)!=17 or set(names)!=EXPECTED:raise ValueError('CASE_SET_INVALID')
    evidence=[];unproven=0
    for t in cases:
        name=t.get('name')
        if t.find('failure') is not None or t.find('error') is not None:raise ValueError('TEST_FAILURE')
        skip=t.find('skipped');outcome='TESTED_EXPECTATION_PASSED'
        if skip is not None:
            if name not in ALLOWED_UNPROVEN or 'BLOCKED_UNPROVEN' not in (skip.get('message','')+(skip.text or '')):
                raise ValueError('UNACCOUNTED_SKIP')
            outcome='BLOCKED_UNPROVEN';unproven+=1
        observations={}
        for p in t.findall('./properties/property'):
            key=p.get('name');value=p.get('value','')
            if key!='observed' or key in observations or not re.fullmatch('[A-Z0-9_]{1,128}',value):
                raise ValueError('PROPERTY_INVALID')
            observations[key]=value
        if skip is None or name=='test_bounded_kernel_exhaustion_unproven':
            if observations.get('observed') not in OBSERVATIONS[name]:raise ValueError('OBSERVATION_MISSING_OR_WRONG')
        evidence.append({'case':name,'outcome':outcome,'observations':observations})
    return {'schema':1,'status':'BLOCKED','assurance':'SYNTHETIC_ONLY','execution_authorized':False,
            'physical_ready':False,'commit_sha':commit,'tested_cases':17-unproven,
            'unproven_cases':unproven,'cases':evidence}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--junit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--commit',required=True);a=p.parse_args()
    with a.junit.open('rb') as f:raw=f.read(2*1024**2+1)
    if len(raw)>2*1024**2:raise ValueError('REPORT_TOO_LARGE')
    report=assess(E.fromstring(raw),a.commit)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,sort_keys=True,indent=2)
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
