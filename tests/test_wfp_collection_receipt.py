import json,hashlib,pytest
from integration.python_containment_evidence import collection_records
from integration import python_containment_evidence as evidence
HEAD='a'*40

def fixture(root):
    ctx=dict(Head=HEAD,Run='12',Attempt='1',Machine='runner',Workspace='D:/fixture')
    p=dict(Schema=1,Phase='PREPARED',Context=ctx,Option=0,Original=0);raw=json.dumps(p,separators=(',',':')).encode();h=hashlib.sha256(raw).hexdigest()
    (root/'wfp-collection-prepared.json').write_bytes(raw)
    for name,row in [('enabled',dict(Schema=1,Phase='ENABLED',Context=ctx,PreparedSha256=h,Observed=1)),('restore-intent',dict(Schema=1,Phase='RESTORE_INTENT',Context=ctx,PreparedSha256=h))]:
        (root/('wfp-collection-'+name+'.json')).write_text(json.dumps(row))
    for action,current,write in [('model',None,False),('enable',1,True),('restore',0,True)]:
        row=dict(schema=1,action=action,status='PASS',reason=None,context=ctx,original=None if action=='model' else 0,current=current,global_option_write_attempted=write,option='FWPM_ENGINE_COLLECT_NET_EVENTS_ONLY',assurance='DEDICATED_DISPOSABLE_GITHUB_VM_DIAGNOSTIC_ONLY',exclusive_vm_assumed=True,host_verified=False,execute_authorized=False,cleanup_authorized=False,external_nonrollback_anchor=False,reboot_recovery_proven=False,physical='0/10 NOT_RUN',g1='BLOCKED')
        (root/('wfp-'+action+'.json')).write_text(json.dumps(row))

def test_owned_logging_records_are_not_physical_authority(tmp_path):
    fixture(tmp_path);collection_records(tmp_path,HEAD,'12','1')

@pytest.mark.parametrize('kind',['wrong-run','changed-value','hash','physical','partial'])
def test_unknown_collection_or_restoration_cannot_pass(tmp_path,kind):
    fixture(tmp_path);p=tmp_path/'wfp-restore.json';v=json.loads(p.read_text())
    if kind=='wrong-run':v['context']['Run']='13'
    elif kind=='changed-value':v['current']=1
    elif kind=='physical':v['execute_authorized']=True
    elif kind=='hash':
        q=tmp_path/'wfp-collection-prepared.json';q.write_bytes(q.read_bytes()+b' ')
    else:(tmp_path/'wfp-collection-enabled.json').unlink()
    p.write_text(json.dumps(v))
    with pytest.raises((ValueError,OSError)):collection_records(tmp_path,HEAD,'12','1')


@pytest.mark.parametrize('name,field',[('prepared','Schema'),('enabled','Observed'),('restore-intent','Schema')])
def test_boolean_record_numbers_are_not_native_integers(tmp_path,name,field):
    fixture(tmp_path);p=tmp_path/('wfp-collection-'+name+'.json');v=json.loads(p.read_text());v[field]=True;p.write_text(json.dumps(v))
    if name=='prepared':
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        for tail in ('enabled','restore-intent'):
            q=tmp_path/('wfp-collection-'+tail+'.json');w=json.loads(q.read_text());w['PreparedSha256']=h;q.write_text(json.dumps(w))
    with pytest.raises(ValueError):collection_records(tmp_path,HEAD,'12','1')


def rebind_context(root, field, value):
    """Rebind every declaration and dependent hash, isolating syntax validation."""
    prepared_path=root/'wfp-collection-prepared.json'
    prepared=json.loads(prepared_path.read_text());prepared['Context'][field]=value
    prepared_path.write_text(json.dumps(prepared,separators=(',',':')))
    digest=hashlib.sha256(prepared_path.read_bytes()).hexdigest()
    for suffix in ('enabled','restore-intent'):
        path=root/('wfp-collection-'+suffix+'.json');row=json.loads(path.read_text())
        row['Context'][field]=value;row['PreparedSha256']=digest;path.write_text(json.dumps(row))
    for action in ('model','enable','restore'):
        path=root/('wfp-'+action+'.json');row=json.loads(path.read_text())
        row['context'][field]=value;path.write_text(json.dumps(row))


@pytest.mark.parametrize('field,value', [
    ('Machine',None),('Machine',True),('Machine',123),('Machine',{'name':'runner'}),
    ('Machine',[]),('Machine',''),('Machine','runner/name'),('Machine','runner name'),
    ('Machine','r\u00fcnner'),('Machine','-runner'),('Machine','a'*254),
    ('Workspace',None),('Workspace',True),('Workspace',{'path':'D:/fixture'}),
    ('Workspace','fixture'),('Workspace','D:fixture'),('Workspace','//server/share/fixture'),
    ('Workspace','D:/fixture/file:stream'),('Workspace','D:/fixture/../other'),
    ('Workspace','D:\\fixture\\..\\other'),('Workspace','D:/fixture\x00name'),
    ('Workspace','D:/fixture\nname'),('Workspace','D:/fixture\x7fname'),
])
def test_consistently_rebound_context_cannot_replace_machine_or_workspace_syntax(tmp_path,field,value):
    fixture(tmp_path);rebind_context(tmp_path,field,value)
    with pytest.raises(ValueError):collection_records(tmp_path,HEAD,'12','1')


def network_host():
    return dict(head=HEAD,run_id='12',attempt='1',status='OBSERVED_NOT_ATTESTED',
                loopback_exit=0,assurance='DIAGNOSTIC_ONLY_NOT_EFFECTIVE_WFP_PROOF')


@pytest.mark.parametrize('value',[False,0.0,None,'0'])
def test_network_host_requires_native_integer_exit_code(value):
    meta=network_host();meta['loopback_exit']=value
    with pytest.raises(ValueError):evidence.validate_network_host(meta,HEAD,'12','1')


def test_valid_network_host_integer_zero_keeps_diagnostic_only_contract():
    evidence.validate_network_host(network_host(),HEAD,'12','1')


@pytest.mark.parametrize('field,value',[('head','b'*40),('status','PASS'),
    ('assurance','PROVEN'),('loopback_exit',1)])
def test_extracted_network_host_check_preserves_existing_requirements(field,value):
    meta=network_host();meta[field]=value
    with pytest.raises(ValueError):evidence.validate_network_host(meta,HEAD,'12','1')
