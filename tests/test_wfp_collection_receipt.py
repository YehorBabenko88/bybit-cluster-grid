import json,hashlib,pytest
from integration.python_containment_evidence import collection_records
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
