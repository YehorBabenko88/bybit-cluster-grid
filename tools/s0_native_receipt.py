"""Pure validator for hosted native-fixture facts; never physical acceptance."""
import re

ROOT_KEYS=frozenset(('scope','fixture','head','normal','deadline','descendant_denied','wrong_hash_rejected','wrong_sid_rejected'))
FACT_KEYS=frozenset(('pid','creation_filetime','exit_code','timed_out','budget_seconds','observed_user_sid','observed_elevated','observed_integrity','observed_admin_enabled','job_member','job_flags','active_limit'))

def _need(condition):
    if not condition:raise ValueError('S0_NATIVE_RECEIPT_BLOCKED')

def _integer(value,minimum,maximum):
    return type(value) is int and minimum<=value<=maximum

def _sid(value):
    if type(value) is not str or len(value)>200 or re.fullmatch(r'S-1-5-21-(?:0|[1-9][0-9]{0,9})-(?:0|[1-9][0-9]{0,9})-(?:0|[1-9][0-9]{0,9})-(?:0|[1-9][0-9]{0,9})',value) is None:return False
    return all(int(part)<=0xffffffff for part in value.split('-')[4:])

def validate_native(value,head,sid=None):
    """Return the same closed record or raise ValueError without logging inputs."""
    _need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) is not None)
    _need(sid is None or _sid(sid))
    _need(type(value) is dict and set(value)==ROOT_KEYS)
    _need(value['scope']=='HOSTED_FIXTURE_NOT_PHYSICAL' and value['fixture'] is True and value['head']==head)
    _need(value['wrong_hash_rejected'] is True and value['wrong_sid_rejected'] is True)
    identities=set();observed_sid=sid
    for label,budget,timeout in (('normal',5,False),('deadline',1,True),('descendant_denied',5,False)):
        fact=value[label];_need(type(fact) is dict and set(fact)==FACT_KEYS)
        _need(_integer(fact['pid'],1,0xffffffff) and _integer(fact['creation_filetime'],1,0x7fffffffffffffff))
        _need(_integer(fact['exit_code'],0,0xffffffff))
        _need((fact['exit_code']!=0) if timeout else fact['exit_code']==0)
        _need(fact['timed_out'] is timeout)
        _need(_integer(fact['budget_seconds'],budget,budget))
        _need(_integer(fact['job_flags'],8200,8200) and _integer(fact['active_limit'],1,1))
        _need(fact['observed_elevated'] is False and fact['observed_admin_enabled'] is False and fact['job_member'] is True)
        _need(fact['observed_integrity']=='S-1-16-8192' and _sid(fact['observed_user_sid']))
        if observed_sid is None:observed_sid=fact['observed_user_sid']
        _need(fact['observed_user_sid']==observed_sid)
        identity=(fact['pid'],fact['creation_filetime']);_need(identity not in identities);identities.add(identity)
    return value
