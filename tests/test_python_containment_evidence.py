import copy
import pytest
from integration.python_containment_evidence import validate, CASES
HEAD='a'*40

def sample():
    child=dict(schema=1,head=HEAD,run_id='12',attempt='1',pid=123,python_version='3.12 synthetic',status='PASS',error=None,cases=[dict(name=n,outcome='PASS') for n in CASES],physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False,whole_system='PARTIAL')
    return dict(schema=1,head=HEAD,run_id='12',attempt='1',status='PASS',reason=None,input_manifest_sha256='a'*64,result_sha256='b'*64,files=15,pid=123,python=child,assurance='HOSTED_PYTHON_NEGATIVE_BOUNDARY_ONLY',host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',whole_system='PARTIAL',network_transport='BLOCKED_NO_CAPABILITIES')

def test_exact_negative_boundary_only():validate(sample(),HEAD,'12','1')
@pytest.mark.parametrize('field,value',[('head','f'*40),('run_id','13'),('pid',True),('status','BLOCKED'),('whole_system','PASS'),('host_verified',True),('execute_authorized',True),('extra','unknown')])
def test_parent_claim_tamper(field,value):
    v=sample();v[field]=value
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')
@pytest.mark.parametrize('field,value',[('pid',124),('head','f'*40),('physical','10/10 PASS'),('cleanup_authorized',True),('extra','unknown')])
def test_child_claim_tamper(field,value):
    v=sample();v['python'][field]=value
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')
@pytest.mark.parametrize('kind',['missing','reordered','failed','duplicate'])
def test_real_component_case_inventory(kind):
    v=sample();rows=v['python']['cases']
    if kind=='missing':rows.pop()
    elif kind=='reordered':rows.reverse()
    elif kind=='failed':rows[-1]['outcome']='FAIL'
    else:rows[-1]=copy.deepcopy(rows[0])
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')


@pytest.mark.parametrize('mutation',['relabel-driver','relabel-grid','missing-grid','extra-grid','changed-grid','unknown-origin'])
def test_input_git_origin_is_not_self_selected(mutation):
    from integration.python_containment_evidence import input_policy
    pins={'driver.py':'A'*64,'Source/grid/worker.py':'B'*64}
    m={'Files':{n:{'Sha256':h,'Length':1} for n,h in pins.items()},'Origins':{n:'git:'+HEAD for n in pins}}
    if mutation=='relabel-driver':m['Origins']['driver.py']='pinned-requirements-resolved'
    elif mutation=='relabel-grid':m['Origins']['Source/grid/worker.py']='setup-python'
    elif mutation=='missing-grid':m['Files'].pop('Source/grid/worker.py');m['Origins'].pop('Source/grid/worker.py')
    elif mutation=='extra-grid':m['Files']['Source/grid/evil.py']={'Sha256':'C'*64,'Length':1};m['Origins']['Source/grid/evil.py']='git:'+HEAD
    elif mutation=='changed-grid':m['Files']['Source/grid/worker.py']['Sha256']='C'*64
    else:m['Files']['Site/evil.py']={'Sha256':'C'*64,'Length':1};m['Origins']['Site/evil.py']='untrusted'
    with pytest.raises(ValueError):input_policy(m,HEAD,pins)
