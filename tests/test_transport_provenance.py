import copy
import pytest
from integration.transport_provenance import validate_transport

HEAD='a'*40

def sample():
    parent=dict(schema=1,head=HEAD,run_id='12',attempt='1',nonce='b'*32,parent_pid=10,child_pid=20,endpoints=[])
    child=[]
    for family,host in ((4,'127.0.0.1'),(6,'::1')):
        for mode in ('listener','bound-not-listening'):
            port=10000+len(child)
            parent['endpoints'].append(dict(family=family,host=host,port=port,mode=mode,ready_utc_ms=1000,host_control='SUCCESS' if mode=='listener' else 'WSA10061'))
            child.append(dict(nonce='b'*32,parent_pid=10,pid=20,family=family,host=host,port=port,mode=mode,started_utc_ms=1001,elapsed_ns=2000000000,local_host=host,local_port=20000+len(child),kind='TIMEOUT',winerror=None,errno=None))
    return parent,child

def test_complete_observation_never_authenticates_policy_or_execution():
    p,c=sample();r=validate_transport(p,c,HEAD,'12','1')
    assert r==dict(status='OBSERVED_NOT_ATTESTED',policy_cause='UNKNOWN',host_verified=False,execute_authorized=False,cleanup_authorized=False)

def test_distinct_address_families_can_share_a_numeric_port():
    p,c=sample();p['endpoints'][2]['port']=p['endpoints'][0]['port'];c[2]['port']=c[0]['port']
    assert validate_transport(p,c,HEAD,'12','1')['policy_cause']=='UNKNOWN'

@pytest.mark.parametrize('field,value',[('nonce','c'*32),('pid',10),('parent_pid',11),('family',True),('host','localhost'),('port',True),('mode','external'),('started_utc_ms',999),('elapsed_ns',-1),('local_host','192.0.2.1'),('local_port',False),('kind','UNKNOWN'),('winerror',True)])
def test_substituted_or_unknown_child_observation_refused(field,value):
    p,c=sample();c[0][field]=value
    with pytest.raises(ValueError):validate_transport(p,c,HEAD,'12','1')

@pytest.mark.parametrize('mutation',['missing','duplicate','unready','ambiguous','wrong-head','foreign-bind','invented-control'])
def test_listener_and_run_provenance_fail_closed(mutation):
    p,c=sample()
    if mutation=='missing':c.pop()
    elif mutation=='duplicate':c[1]=copy.deepcopy(c[0])
    elif mutation=='unready':p['endpoints'][0]['ready_utc_ms']=None
    elif mutation=='ambiguous':p['endpoints'][1]['port']=p['endpoints'][0]['port']
    elif mutation=='wrong-head':p['head']='f'*40
    elif mutation=='foreign-bind':p['endpoints'][0]['host']='0.0.0.0'
    else:p['endpoints'][1]['host_control']='SUCCESS'
    with pytest.raises(ValueError):validate_transport(p,c,HEAD,'12','1')
