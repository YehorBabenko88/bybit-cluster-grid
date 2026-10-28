import copy
import io
import json
import zipfile
import pytest
from tools.s0_independent_acceptance import (archive_members, check, check_context,
    junit, native, sha, strict_json, REQUIRED_SOURCES)

CTX = dict(head='a'*40,tree='b'*40,run_id='123',attempt='2')

def raw(value): return json.dumps(value).encode()

def zip_bytes(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for name,data in files.items(): archive.writestr(name,data)
    return out.getvalue()


def fixture():
    authority = dict(s0_execute=False,g1_execute=False,cleanup=False)
    sources = {name:b'reviewed source' for name in REQUIRED_SOURCES}
    sources['integration/s0_inventory.json'] = raw(dict(hosted_nodes=['tests/test_s0.py::test_one']))
    pins = {name:sha(data) for name,data in sources.items() if name in REQUIRED_SOURCES}
    files = {('runtime/App/'+name if name.startswith('s0_smoke/') else name):sources[name] for name in pins}
    files['native/S0Launcher.dll'] = b'never execute'
    manifest = dict(CTX,schema=1,profile='PHYSICAL_SMOKE_S0',authority=authority,python='3.12.1',source=pins,files={n:dict(size=len(d),sha256=sha(d)) for n,d in files.items()})
    package = zip_bytes(dict(files,**{'s0-package.json':raw(manifest)}))
    receipt = dict(CTX,schema=1,profile='PHYSICAL_SMOKE_S0',authority=authority,python='3.12.1',source=pins,package='package.zip',sha256=sha(package),size=len(package))
    xml = ('<testsuites><testsuite tests="1" errors="0" failures="0" skipped="0" head="'+CTX['head']+'" run_id="123" attempt="2"><testcase classname="tests.test_s0" name="test_one" /></testsuite></testsuites>').encode()
    line = raw(dict(CTX,node='tests/test_s0.py::test_one',status='TEST_PASS',g1_execute=False,physical_sid_acl='0/10 NOT_RUN'))+b'\n'
    idx = dict(CTX,phase='hosted',scope='SYNTHETIC_OFFLINE_OR_HOSTED_NOT_PHYSICAL',nodes=['tests/test_s0.py::test_one'],tests=1,subtests=0,g1_execute=False,physical_sid_acl='0/10 NOT_RUN',sources=pins,files={'hosted.xml':sha(xml),'hosted.jsonl':sha(line)})
    nr = dict({k:v for k,v in CTX.items() if k != 'tree'},scope='HOSTED_FIXTURE_NOT_PHYSICAL',fixture=True,token_probe_cases=14,wrong_hash_rejected=True,wrong_sid_rejected=True,source_sha256=pins,binary_sha256={'S0Launcher.dll':sha(files['native/S0Launcher.dll'])})
    for i,(label,budget,timeout) in enumerate((('normal',5,False),('deadline',1,True),('descendant_denied',5,False)),1):
        nr[label] = dict(pid=i,creation_filetime=100+i,exit_code=0,timed_out=timeout,budget_seconds=budget,observed_user_sid='S-1-5-21-1-2-3-4',observed_elevated=False,observed_integrity='S-1-16-8192',observed_admin_enabled=False,job_member=True,job_flags=8200,active_limit=1)
    outer = {'s0-package/package-receipt.json':raw(receipt),'s0-package/package.zip':package,'s0-results/hosted-sha256.json':raw(idx),'s0-results/hosted.xml':xml,'s0-results/hosted.jsonl':line,'s0-results/native-launcher.json':raw(nr),'s0-results/portable.json':raw(dict(CTX,physical='NOT_RUN',runs=[],status='PORTABLE_PLAN_AND_IMPORTS_PASS',package_sha256=sha(package),s0_execute=False,g1_execute=False))}
    outer['s0-results/public-probe.json'] = raw(dict({k:v for k,v in CTX.items() if k != 'tree'},schema=1,duration_ms=100,detail=None,last_operation='FRAME_RECEIVE',scope='PUBLIC_HOSTED_DIAGNOSTIC_ONLY',physical_ready=False,s0_execute=False,g1_execute=False,counts=dict(subscribe_ack=False,book_samples=0,trade_samples=0,samples=0),samples=[],error='TIMEOUT',http_status=None,status='BLOCKED'))
    for role in ('LS5','PC4'):
        prefix = 's0-results/component-fixture/'+role+'/'
        summary = raw(dict({k:v for k,v in CTX.items() if k != 'attempt'},schema=1,package_sha256='b'*64,run_id='fixture-run',role=role,status='BLOCKED_OR_PARTIAL',physical_sid_acl='0/10 NOT_RUN',deployment='NO-GO',g1_execute=False,cleanup_authorized=False,scope='S0_PUBLIC_ONLY_NOT_GRID_ACCEPTANCE',error=None,result=dict(final=True,stats={'trade_count':0},heartbeats=3)))
        outer[prefix+'summary.json'] = summary
        previous='0'*64; lines=[]
        for number,kind in enumerate(('started','finished'),1):
            value = {} if kind == 'started' else dict(result=strict_json(summary)['result'],error=None)
            row = dict(seq=number,previous=previous,payload=dict(head=CTX['head'],run_id='fixture-run',role=role,kind=kind,utc_ms=number,value=value))
            row['sha256']=sha(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()); previous=row['sha256']; lines.append(raw(row))
        result_xml=('<testsuite tests="1" errors="0" skipped="0" failures="1" head="'+CTX['head']+'" run_id="fixture-run"><testcase name="partial"><failure /></testcase></testsuite>').encode()
        component = {'summary.json':summary,'events.jsonl':b'\n'.join(lines)+b'\n','claim.json':b'{}','results.xml':result_xml}
        for name,data in component.items(): outer[prefix+name] = data
        outer[prefix+'sha256.json'] = raw(dict(schema=1,package_sha256='b'*64,head=CTX['head'],run_id='fixture-run',role=role,g1_execute=False,cleanup_authorized=False,files={n:sha(d) for n,d in component.items()}))
    return outer,sources


def accepted(outer,sources,context=None):
    payload=zip_bytes(outer)
    return check(payload,sha(payload),context or CTX,sources.__getitem__)


def test_synthetic_pass_is_never_approval():
    outer,sources=fixture(); result=accepted(outer,sources)
    assert result['status']=='OFFLINE_EVIDENCE_CHECK_PASS_NOT_APPROVAL'
    assert result['approval']=='BLOCKED' and result['execute']=='NOT_AUTHORIZED'

@pytest.mark.parametrize('field',['head','tree','run_id','attempt'])
def test_expected_context_bound(field):
    outer,sources=fixture(); context=dict(CTX); context[field]='c'*40 if field in ('head','tree') else '9'
    with pytest.raises(ValueError): accepted(outer,sources,context)

def test_external_outer_digest_not_receipt_digest():
    outer,sources=fixture(); payload=zip_bytes(outer)
    with pytest.raises(ValueError): check(payload,'0'*64,CTX,sources.__getitem__)

def test_duplicate_json_rejected():
    with pytest.raises(ValueError): strict_json(b'{"x":1,"x":2}')

@pytest.mark.parametrize('name',['../a','/a','a\\b','a//b','a/./b','C:a'])
def test_archive_paths_rejected(name):
    payload = zip_bytes({'aXb':b'a'}).replace(b'aXb',name.encode()) if name == 'a\\b' else zip_bytes({name:b'a'})
    with pytest.raises(ValueError): archive_members(payload)

def test_case_duplicate_archive_rejected():
    with pytest.raises(ValueError): archive_members(zip_bytes({'A':b'a','a':b'b'}))

@pytest.mark.parametrize('mutation',['payload','manifest','physical','skip','missing_fact','coerced_bool','attempt','counter'])
def test_authentic_but_bad_evidence_rejected(mutation):
    outer,sources=fixture()
    if mutation in ('payload','manifest'):
        files=archive_members(outer['s0-package/package.zip'])
        if mutation=='payload': files['native/S0Launcher.dll']=b'changed'
        else:
            m=strict_json(files['s0-package.json']); m['head']='c'*40; files['s0-package.json']=raw(m)
        package=zip_bytes(files); outer['s0-package/package.zip']=package
        receipt=strict_json(outer['s0-package/package-receipt.json']); receipt.update(sha256=sha(package),size=len(package)); outer['s0-package/package-receipt.json']=raw(receipt)
    elif mutation=='skip':
        outer['s0-results/hosted.xml']=outer['s0-results/hosted.xml'].replace(b'<testcase ',b'<skipped/><testcase ')
        idx=strict_json(outer['s0-results/hosted-sha256.json']); idx['files']['hosted.xml']=sha(outer['s0-results/hosted.xml']); outer['s0-results/hosted-sha256.json']=raw(idx)
    elif mutation in ('missing_fact','coerced_bool','attempt'):
        n=strict_json(outer['s0-results/native-launcher.json'])
        if mutation=='missing_fact': del n['deadline']['job_member']
        elif mutation=='coerced_bool': n['normal']['observed_elevated']=0
        else: n['attempt']='1'
        outer['s0-results/native-launcher.json']=raw(n)
    else:
        path='s0-results/component-fixture/PC4/summary.json'; s=strict_json(outer[path])
        if mutation=='physical': s['status']='PUBLIC_SMOKE_OBSERVED'
        else: s['result']['heartbeats']=4
        outer[path]=raw(s)
        idxpath='s0-results/component-fixture/PC4/sha256.json'; idx=strict_json(outer[idxpath]); idx['files']['summary.json']=sha(outer[path]); outer[idxpath]=raw(idx)
    with pytest.raises((ValueError,KeyError)): accepted(outer,sources)

def test_junit_subtests_and_stale_identity():
    xml=b'<testsuites><testsuite tests="3" errors="0" failures="0" skipped="0" head="'+CTX['head'].encode()+b'" run_id="123" attempt="2"><testcase classname="c" name="n"/></testsuite></testsuites>'
    junit(xml,CTX,[('c','n')],2)
    with pytest.raises(ValueError): junit(xml,CTX,[('c','n')],1)
    with pytest.raises(ValueError): junit(xml,dict(CTX,attempt='1'),[('c','n')],2)


def test_source_provider_prevents_rebinding_source():
    outer,sources=fixture(); sources['s0_smoke/cli.py']=b'other reviewed source'
    with pytest.raises(ValueError): accepted(outer,sources)

def test_unknown_native_boolean_rejected():
    outer,sources=fixture(); path='s0-results/native-launcher.json'
    n=strict_json(outer[path]); n['approval']=True; outer[path]=raw(n)
    with pytest.raises(ValueError): accepted(outer,sources)

def test_public_probe_cannot_claim_physical_ready():
    outer,sources=fixture(); path='s0-results/public-probe.json'
    n=strict_json(outer[path]); n['physical_ready']=True; outer[path]=raw(n)
    with pytest.raises(ValueError): accepted(outer,sources)


@pytest.mark.parametrize('limit,value',[('LIMIT',10),('ENTRY',0),('COUNT',0)])
def test_archive_resource_limits(monkeypatch,limit,value):
    import tools.s0_independent_acceptance as checker
    payload=zip_bytes({'x':b'payload'})
    monkeypatch.setattr(checker,limit,value)
    with pytest.raises(ValueError): archive_members(payload)

def test_duplicate_inner_manifest_json_rejected():
    outer,sources=fixture(); files=archive_members(outer['s0-package/package.zip'])
    files['s0-package.json']=b'{"head":"a","head":"b"}'
    package=zip_bytes(files); outer['s0-package/package.zip']=package
    receipt=strict_json(outer['s0-package/package-receipt.json']); receipt.update(sha256=sha(package),size=len(package)); outer['s0-package/package-receipt.json']=raw(receipt)
    with pytest.raises(ValueError): accepted(outer,sources)

def test_missing_source_requirement_rejected():
    outer,sources=fixture(); files=archive_members(outer['s0-package/package.zip'])
    m=strict_json(files['s0-package.json']); del m['source']['s0_smoke/cli.py']; files['s0-package.json']=raw(m)
    package=zip_bytes(files); outer['s0-package/package.zip']=package
    receipt=strict_json(outer['s0-package/package-receipt.json']); receipt.update(sha256=sha(package),size=len(package),source=m['source']); outer['s0-package/package-receipt.json']=raw(receipt)
    with pytest.raises(ValueError): accepted(outer,sources)
