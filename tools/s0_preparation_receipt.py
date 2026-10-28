"""Closed aggregate hosted-token evidence; grants no physical authorization."""
import re

TOKEN_SOURCES=('installer/physical-smoke-s0/TokenObserver.cs','installer/physical-smoke-s0-tests/TokenObserverTests.cs','installer/physical-smoke-s0-tests/TokenObserverFixture.cs')
TOKEN_KEYS=frozenset(('scope','component','head','status','pure_cases','parent_admin_rejected','standard_primary_accepted','sid_matches','wrong_sid_rejected','medium','elevated','group_count','privilege_count','enabled_privilege_count','physical_acceptance'))

def _need(ok):
    if not ok:raise ValueError('S0_TOKEN_RECEIPT_BLOCKED')

def _hex(value,length):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None

def validate_token(value,head):
    _need(_hex(head,40) and type(value) is dict and set(value)==TOKEN_KEYS)
    _need(value['scope']=='HOSTED_FIXTURE_NOT_PHYSICAL' and value['component']=='TOKEN_OBSERVER' and value['status']=='TEST_PASS' and value['head']==head)
    _need(all(value[k] is True for k in ('pure_cases','parent_admin_rejected','standard_primary_accepted','sid_matches','wrong_sid_rejected','medium')))
    _need(value['elevated'] is False and value['physical_acceptance'] is False)
    for key,minimum,maximum in [('group_count',1,4096),('privilege_count',0,4096),('enabled_privilege_count',0,1)]:
        _need(type(value[key]) is int and minimum<=value[key]<=maximum)
    _need(value['enabled_privilege_count']<=value['privilege_count'])
    return value

def validate_token_record(value,context,sources,dll_sha256):
    _need(type(context) is dict and set(context)=={'head','run_id','attempt'})
    _need(_hex(context['head'],40) and all(type(context[k]) is str and re.fullmatch('[1-9][0-9]{0,19}',context[k]) is not None for k in ('run_id','attempt')))
    extra={'run_id','attempt','binary_sha256','source_sha256'}
    _need(type(value) is dict and set(value)==TOKEN_KEYS|extra)
    validate_token({k:v for k,v in value.items() if k not in extra},context['head'])
    _need(all(value[k]==v and type(value[k]) is str for k,v in context.items()))
    _need(type(sources) is dict and set(sources)==set(TOKEN_SOURCES) and all(_hex(v,64) for v in sources.values()))
    _need(type(value['source_sha256']) is dict and value['source_sha256']==sources)
    binaries=value['binary_sha256'];_need(type(binaries) is dict and set(binaries)=={'S0Launcher.dll','TokenObserverFixture.exe'} and all(_hex(v,64) for v in binaries.values()))
    _need(_hex(dll_sha256,64) and binaries['S0Launcher.dll']==dll_sha256)
    return value
