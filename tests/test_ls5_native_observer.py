from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]


def test_observer_requires_relative_no_follow_chain():
    source='\n'.join(p.read_text(encoding='utf-8-sig') for p in (ROOT/'installer/native-acl-observer').glob('*.cs'))
    for api in ['NtCreateFile','RootDirectory','OBJ_DONT_REPARSE','GetSecurityInfo','AccessCheck','DuplicateTokenEx','GetTokenInformation']:
        assert api in source
    for forbidden in ['SetSecurityInfo','SetNamedSecurityInfo','AdjustTokenPrivileges','LogonUser','CreateProcess']:
        assert forbidden not in source


def test_ci_exact_head_and_receipts_required():
    s=(ROOT/'.github/workflows/ls5-native-observer.yml').read_text()
    for marker in ['github.event.pull_request.head.sha','required-observer-gate','--verify','JSONL','SHA256']:
        assert marker in s
    assert 'Remove-Item' not in s and 'fetch-depth: 0' in s


def test_ci_alternative_pool_is_literal_github_hosted_only():
    s=(ROOT/'.github/workflows/ls5-native-observer.yml').read_text()
    assert "inputs.windows_2022 == true && 'windows-2022' || 'windows-latest'" in s
    assert 'type: boolean' in s and 'runs-on: ${{ inputs.' not in s and 'self-hosted' not in s


def test_executor_authority_stays_blocked():
    s=(ROOT/'installer/ls5-acl-remediation.ps1').read_text()
    assert "if($Apply){throw 'EXECUTE_NOT_AUTHORIZED" in s


def receipt():
    import hashlib,json
    token=dict(user='S-1-5-21-1-2-3-1001',elevated=True,integrity=12288,groups=[dict(sid='S-1-1-0',attributes=4)])
    raw=dict(user=token['user'],elevated=True,level=12288,groups=[dict(Sid='S-1-1-0',Attributes=4)])
    token['fingerprint']=hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper()
    chain=[dict(depth=i,identity=dict(volume=1,fileId=f'{i+1:032X}',links=1,attributes=16 if i<3 else 0),
        owner='S-1-5-18',group='S-1-5-18',descriptorSha256='A'*64,protected=True,
        aces=[dict(sid='S-1-5-18',mask=0x1f01ff,flags=0,type='AccessAllowed')],
        effectiveRights={k:'DACL_ALLOW' for k in ['DELETE','WRITE_DAC','WRITE_OWNER','WRITE_DATA','APPEND_DATA','DELETE_CHILD']}) for i in range(4)]
    del chain[-1]['effectiveRights']['DELETE_CHILD']
    report=dict(schema=1,reason='ALL_PRINCIPALS_WRITERS_AND_BOOTSTRAP_NOT_PROVEN',fault_injection=False,status='BLOCKED',observation='OBSERVED',effectiveRightsStatus='BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN',token=token,chain=chain)
    flags={k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']}
    report.update(flags)
    return dict(case='ordinary-read-only-observation',head='a'*40,run_id='1',attempt='1',outcome='PASS',kind='HOSTED_GUID_OBSERVER_TEST',payload=dict(code=0,value=report),details=None,**flags)


def test_valid_receipt_has_no_authority():
    from installer.native_observer_ci import verify_rows
    r=receipt();verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['missing-token','bad-group-flags','token-digest','ace-sid','ace-kind','ace-bool-mask'])
def test_native_receipt_rejects_unknown_security_facts(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();v=r['payload']['value']
    if fault=='missing-token':del v['token']
    if fault=='bad-group-flags':v['token']['groups'][0]['attributes']=0x14
    if fault=='token-digest':v['token']['fingerprint']='B'*64
    if fault=='ace-sid':v['chain'][0]['aces'][0]['sid']='BUILTIN\\Users'
    if fault=='ace-kind':v['chain'][0]['aces'][0]['type']='Callback'
    if fault=='ace-bool-mask':v['chain'][0]['aces'][0]['mask']=True
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['row-authority','report-authority','wrong-head','wrong-run','wrong-attempt','bool-exit','no-chain','symlink','hardlink','missing-right','native-error','skip'])
def test_native_evidence_forgery_is_rejected(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();v=r['payload']['value']
    if fault=='row-authority':r['host_verified']=True
    if fault=='report-authority':v['apply_authorized']=True
    if fault=='wrong-head':r['head']='b'*40
    if fault=='wrong-run':r['run_id']='2'
    if fault=='wrong-attempt':r['attempt']='2'
    if fault=='bool-exit':r['payload']['code']=False
    if fault=='no-chain':v['chain']=[]
    if fault=='symlink':v['chain'][0]['identity']['attributes']|=0x400
    if fault=='hardlink':v['chain'][-1]['identity']['links']=2
    if fault=='missing-right':del v['chain'][0]['effectiveRights']['WRITE_DAC']
    if fault=='native-error':r['payload']['code']=2
    if fault=='skip':r['outcome']='SKIP'
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['zero-id','different-volume','file-parent','missing-delete-child','duplicate-id','bool-depth'])
def test_inconsistent_native_chain_is_rejected(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();chain=r['payload']['value']['chain']
    if fault=='zero-id':chain[0]['identity']['fileId']='0'*32
    if fault=='different-volume':chain[1]['identity']['volume']=2
    if fault=='file-parent':chain[0]['identity']['attributes']=0
    if fault=='missing-delete-child':del chain[0]['effectiveRights']['DELETE_CHILD']
    if fault=='duplicate-id':chain[1]['identity']['fileId']=chain[0]['identity']['fileId']
    if fault=='bool-depth':chain[0]['depth']=False
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


def test_session_drains_output_before_waiting():
    source=(ROOT/'installer/tests/test-native-acl-observer.ps1').read_text()
    body=source.split('function Recheck(',1)[1].split('\ntry {',1)[0]
    assert body.index('ReadToEndAsync') < body.index('WaitForExit')


@pytest.mark.parametrize('fault',['schema','extra-row','extra-report'])
def test_unknown_evidence_schema_is_rejected(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt()
    if fault=='schema':r['payload']['value']['schema']=2
    if fault=='extra-row':r['physical_pass']=True
    if fault=='extra-report':r['payload']['value']['deployment_authorized']=True
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['token-extra','duplicate-group','identity-extra','negative-links','rights-extra','observation-extra'])
def test_security_subschemas_are_closed(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();v=r['payload']['value'];o=v['chain'][-1]
    if fault=='token-extra':v['token']['mic_verified']=True
    if fault=='duplicate-group':
        import hashlib,json
        t=v['token'];t['groups']*=2
        raw=dict(user=t['user'],elevated=t['elevated'],level=t['integrity'],groups=[dict(Sid=g['sid'],Attributes=g['attributes']) for g in t['groups']])
        t['fingerprint']=hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper()
    if fault=='identity-extra':o['identity']['authenticated']=True
    if fault=='negative-links':v['chain'][0]['identity']['links']=-1
    if fault=='rights-extra':o['effectiveRights']['MIC']='DACL_ALLOW'
    if fault=='observation-extra':o['provenance_verified']=True
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['head','attempt','authority','case','crash-claim','authentication-claim'])
def test_transaction_receipt_cannot_promote_fixture_to_authority(fault):
    from installer.native_observer_ci import verify_transaction
    r=dict(schema=1,status='OFFLINE_FIXTURE_PASS',head='a'*40,run_id='1',attempt='1',
        snapshots=[],cases=[dict(case='x',outcome='PASS',kind='HOSTED_GUID_TRANSACTION_TEST',head='a'*40,run_id='1',attempt='1',
                    **{k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']})],
        crash_model='SIMULATED_BARRIER_REOPEN_RETAINED_ROOT',journal_authentication='NOT_PROVEN',durable_antirollback='BLOCKED',
        **{k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']})
    if fault=='head':r['head']='b'*40
    if fault=='attempt':r['cases'][0]['attempt']='2'
    if fault=='authority':r['apply_authorized']=True
    if fault=='case':r['cases'][0]['case']='y'
    if fault=='crash-claim':r['crash_model']='POWER_LOSS_PROVEN'
    if fault=='authentication-claim':r['journal_authentication']='AUTHENTICATED'
    with pytest.raises(ValueError):verify_transaction(r,['x'],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['none','head','attempt','skip-node','counter','duplicate','entity'])
def test_independent_junit_inspector(fault):
    from installer.native_observer_artifacts import verify_xml
    raw=b'<testsuite head="'+b'a'*40+b'" run_id="1" attempt="1" tests="1" failures="0" errors="0" skipped="0"><testcase classname="c" name="x"/></testsuite>'
    if fault=='head':raw=raw.replace(b'a'*40,b'b'*40)
    if fault=='attempt':raw=raw.replace(b'attempt="1"',b'attempt="2"')
    if fault=='skip-node':raw=raw.replace(b'name="x"/>',b'name="x"><skipped/></testcase>')
    if fault=='counter':raw=raw.replace(b'tests="1"',b'tests="0"')
    if fault=='duplicate':raw=raw.replace(b'</testsuite>',b'<testcase classname="c" name="x"/></testsuite>')
    if fault=='entity':raw=b'<!DOCTYPE foo>'+raw
    if fault=='none':verify_xml(raw,[('c','x')],'a'*40,'1','1')
    else:
        with pytest.raises(ValueError):verify_xml(raw,[('c','x')],'a'*40,'1','1')


def tx_snapshot():
    import base64,hashlib,json
    identity=lambda n,a:dict(Volume=1,FileId=f'{n:032X}',Links=1,Attributes=a)
    binding=dict(Schema=1,Head='a'*40,Run='1',Attempt='1',Id='00000000-0000-0000-0000-000000000001',
        Root=identity(1,16),Target=identity(2,128),Old=base64.b64encode(b'old'*10).decode(),New=base64.b64encode(b'new'*10).decode())
    previous='0'*64;lines=[]
    for n,phase in enumerate(['PREPARED','INTENT','APPLIED','VERIFIED','COMMITTED']):
        row=dict(Binding=binding,Sequence=n,Phase=phase,Previous=previous)
        previous=hashlib.sha256(json.dumps(row,separators=(',',':')).encode()).hexdigest().upper()
        row['Digest']=previous;lines.append(json.dumps(row,separators=(',',':')))
    return dict(case='commit-native-readback',binding=binding,journal_id=identity(3,128),root_observed=binding['Root'],
        target_observed=binding['Target'],current_descriptor=binding['New'],journal_base64=base64.b64encode(('\n'.join(lines)+'\n').encode()).decode())


@pytest.mark.parametrize('fault',['none','journal-torn','journal-digest','identity','descriptor','replay','unexplained-rollback','auto-inherited-control-drift'])
def test_transaction_snapshot_bytes_are_independently_checked(fault):
    import base64
    from installer.native_observer_ci import verify_snapshot
    s=tx_snapshot()
    if fault=='journal-torn':s['journal_base64']=base64.b64encode(base64.b64decode(s['journal_base64'])[:-1]).decode()
    if fault=='journal-digest':s['journal_base64']=base64.b64encode(base64.b64decode(s['journal_base64']).replace(b'PREPARED',b'VERIFIED')).decode()
    if fault=='identity':s['target_observed']={**s['target_observed'],'Volume':2}
    if fault=='descriptor':s['current_descriptor']='AAAA'
    if fault=='auto-inherited-control-drift':
        raw=bytearray(base64.b64decode(s['binding']['New']));raw[3]^=4
        s['current_descriptor']=base64.b64encode(raw).decode()
    if fault=='replay':s['binding']={**s['binding'],'Attempt':'2'}
    if fault=='unexplained-rollback':s['current_descriptor']=s['binding']['Old']
    if fault=='none':verify_snapshot(s,'a'*40,'1','1')
    else:
        with pytest.raises(ValueError):verify_snapshot(s,'a'*40,'1','1')


def synthetic_archive():
    """Non-executable bytes only. Mocks Git blob reads, never native observations."""
    import base64,hashlib,io,json,xml.etree.ElementTree as E,zipfile
    flags={k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']}
    inventory=dict(source_files=['tests/fixtures/native_observer_inventory.json','fixture.cs'],native_cases=['ordinary-read-only-observation'],
        pure_cases=['p'],transaction_cases=['t'],journal_cases=['j'],python_nodes=['tests/x.py::test_x'],python_junit_cases=[['tests.x','test_x']])
    blobs={'tests/fixtures/native_observer_inventory.json':json.dumps(inventory).encode(),'fixture.cs':b'SYNTHETIC_SOURCE'}
    files={};put=lambda n,x:files.__setitem__(n,json.dumps(x,separators=(',',':')).encode())
    files['native-observer.jsonl']=json.dumps(receipt()).encode()+b'\n'
    put('native-observer-pure.json',dict(schema=1,status='OFFLINE_TEST_PASS',cases=[dict(case='p',outcome='PASS',**flags)],**flags))
    put('native-observer-journal-model.json',dict(status='OFFLINE_TEST_PASS',kind='SYNTHETIC_JOURNAL_MODEL',cases=['j'],**flags))
    snapshots=[]
    for n,case in enumerate(['commit-native-readback']+['simulated-reopen-'+s for s in ('PREPARED','INTENT','AFTER_SET','APPLIED','VERIFIED','COMMITTED')]):
        s=tx_snapshot();s['case']=case;b=s['binding'];b['Id']=f'00000000-0000-0000-0000-{n+1:012x}'
        b['Root']['FileId']=f'{3*n+1:032X}';b['Target']['FileId']=f'{3*n+2:032X}';s['journal_id']['FileId']=f'{3*n+3:032X}'
        phases=['PREPARED','INTENT','APPLIED','VERIFIED','COMMITTED']
        if case=='simulated-reopen-PREPARED':phases=phases[:1]
        elif case=='simulated-reopen-INTENT':phases=phases[:2]
        elif case!='commit-native-readback':phases+=['RESTORE_INTENT','RESTORED']
        previous='0'*64;lines=[]
        for i,p in enumerate(phases):
            row=dict(Binding=b,Sequence=i,Phase=p,Previous=previous)
            previous=hashlib.sha256(json.dumps(row,separators=(',',':')).encode()).hexdigest().upper();row['Digest']=previous;lines.append(json.dumps(row,separators=(',',':')))
        s['journal_base64']=base64.b64encode(('\n'.join(lines)+'\n').encode()).decode()
        s['current_descriptor']=b['New'] if case=='commit-native-readback' else b['Old'];snapshots.append(s)
    tx=dict(schema=1,status='OFFLINE_FIXTURE_PASS',head='a'*40,run_id='1',attempt='1',cases=[dict(case='t',outcome='PASS',kind='HOSTED_GUID_TRANSACTION_TEST',head='a'*40,run_id='1',attempt='1',**flags)],
        snapshots=snapshots,crash_model='SIMULATED_BARRIER_REOPEN_RETAINED_ROOT',journal_authentication='NOT_PROVEN',durable_antirollback='BLOCKED',**flags)
    put('native-observer-transaction.json',tx);files['native-observer-transaction.jsonl']=json.dumps(tx['cases'][0]).encode()+b'\n'
    files['native-observer-python.jsonl']=json.dumps(dict(case='tests/x.py::test_x',head='a'*40,run_id='1',attempt='1',outcome='PASS',kind='SYNTHETIC_PYTHON',**flags)).encode()+b'\n'
    for suffix,name,classname in [('', 'ordinary-read-only-observation','hosted_guid_observer'),('-pure','p','synthetic_managed_policy'),('-transaction','t','hosted_guid_transaction'),('-journal-model','j','synthetic_journal_model'),('-python','test_x','tests.x')]:
        suite=E.Element('testsuite',head='a'*40,run_id='1',attempt='1',tests='1',failures='0',errors='0',skipped='0')
        E.SubElement(suite,'testcase',name=name,classname=classname);files['native-observer'+suffix+'.xml']=E.tostring(suite)
    receipt_index=dict(head='a'*40,run_id='1',attempt='1',physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO',bootstrap_handoff='BLOCKED_NOT_CONSUMED',
        native_cases=1,pure_cases=1,transaction_cases=1,journal_model_cases=1,source_sha256={k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()},
        artifacts={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    for component,stem,key in [('native-acl-observer','NativeAclObserver','binary_sha256'),('native-acl-transaction-fixture','NativeAclTransactionFixture','transaction_binary_sha256')]:
        hashes={}
        for suffix in ('.exe','.dll','.deps.json','.runtimeconfig.json'):
            name=stem+suffix;content=b'SYNTHETIC_NOT_EXECUTABLE';hashes[name]=hashlib.sha256(content).hexdigest();files[f'installer/{component}/bin/Release/net8.0-windows/{name}']=content
        receipt_index[key]=hashes
    put('native-observer-receipt.json',receipt_index)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    raw=out.getvalue();metadata=dict(run=dict(head_sha='a'*40,id=1,run_attempt=1,status='completed',conclusion='success'),
        artifact=dict(name='synthetic',id=1,expired=False,workflow_run=dict(head_sha='a'*40,id=1),digest='sha256:'+hashlib.sha256(raw).hexdigest()))
    return raw,metadata,blobs


@pytest.mark.parametrize('fault',['none','zip-digest','head','attempt','queued','source-digest'])
def test_downloaded_archive_consistency_is_not_physical_authority(fault,monkeypatch):
    from installer.native_observer_artifacts import inspect_archive
    raw,metadata,blobs=synthetic_archive()
    if fault=='zip-digest':metadata['artifact']['digest']='sha256:'+'0'*64
    if fault=='head':metadata['run']['head_sha']='b'*40
    if fault=='attempt':metadata['run']['run_attempt']=2
    if fault=='queued':metadata['run'].update(status='queued',conclusion=None)
    if fault=='source-digest':blobs['fixture.cs']=b'CHANGED'
    monkeypatch.setattr('installer.native_observer_artifacts.subprocess.check_output',lambda args,**kw:blobs[args[-1].split(':',1)[1]])
    if fault=='none':
        result=inspect_archive(raw,metadata,'a'*40,'1','1','synthetic')
        assert result['status']=='OFFLINE_ARTIFACT_CONSISTENT' and result['custody_authenticated'] is False and result['apply_authorized'] is False
    else:
        with pytest.raises(ValueError):inspect_archive(raw,metadata,'a'*40,'1','1','synthetic')


def test_transaction_snapshots_cannot_replay_another_scenario():
    import copy,io,json,zipfile
    from installer.native_observer_ci import verify_transaction
    raw,_,_=synthetic_archive()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:tx=json.loads(z.read('native-observer-transaction.json'))
    tx['snapshots'][4]=copy.deepcopy(tx['snapshots'][3]);tx['snapshots'][4]['case']='simulated-reopen-APPLIED'
    with pytest.raises(ValueError):verify_transaction(tx,['t'],'a'*40,'1','1')


def test_managed_receipt_rejects_extra_attestation():
    from installer.native_observer_ci import verify_pure
    p=dict(schema=1,status='OFFLINE_TEST_PASS',cases=[],custody_authenticated=True,
           **{k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']})
    with pytest.raises(ValueError):verify_pure(p,[])
