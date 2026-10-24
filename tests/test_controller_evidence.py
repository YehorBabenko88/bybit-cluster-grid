"""Synthetic receipt mutations only; no Windows APIs or physical execution."""
import copy
import json
import pytest
from integration import controller_evidence as c

HEAD='a'*40


def sample(kind='MODEL_TESTS'):
    return dict(schema=1,kind=kind,status='PASS',reason=None,
        cases=[dict(name=n,outcome='PASS') for n in (c.MODEL if kind=='MODEL_TESTS' else c.NATIVE)],
        head=HEAD,repository='YehorBabenko88/bybit-cluster-grid',run_id='12',attempt='2',
        host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',g1='BLOCKED')


@pytest.mark.parametrize('kind',['MODEL_TESTS','HOSTED_FIXTURE_TESTS'])
def test_exact_inventory(kind):
    assert c.validate(sample(kind),kind,HEAD,'12','2') == (c.MODEL if kind=='MODEL_TESTS' else c.NATIVE)


@pytest.mark.parametrize('field,value',[
    ('schema',True),('head','b'*40),('run_id','13'),('attempt','3'),
    ('repository','attacker/repo'),('status','SKIPPED'),('reason','ignored'),
    ('host_verified',True),('execute_authorized',1),('cleanup_authorized',True),
    ('physical','10/10 PASS'),('g1','PASS'),('cases',[]),('extra','unknown')])
def test_tampered_fields(field,value):
    v=sample();v[field]=value
    with pytest.raises(ValueError):c.validate(v,'MODEL_TESTS',HEAD,'12','2')


@pytest.mark.parametrize('mutation',['duplicate','reorder','skip','xfail'])
def test_case_mutation(mutation):
    v=sample()
    if mutation=='duplicate':v['cases'][-1]=copy.deepcopy(v['cases'][0])
    elif mutation=='reorder':v['cases'].reverse()
    else:v['cases'][0]['outcome']=mutation.upper()
    with pytest.raises(ValueError):c.validate(v,'MODEL_TESTS',HEAD,'12','2')


def test_duplicate_json_keys(tmp_path):
    p=tmp_path/'fixture.json';p.write_text('{"status":"FAIL","status":"PASS"}')
    with pytest.raises(ValueError):c.load(p)


@pytest.mark.parametrize('tamper',['manifest','xml','jsonl','source'])
def test_downloaded_receipt_reinspection(tmp_path,monkeypatch,tamper):
    monkeypatch.setattr(c,'source_hashes',lambda head:{'source':'a'*64})
    for file,kind in [('model.json','MODEL_TESTS'),('native.json','HOSTED_FIXTURE_TESTS')]:
        (tmp_path/file).write_text(json.dumps(sample(kind)),encoding='utf-8')
    assert c.receipt(tmp_path,HEAD,'12','2',create=True)['tests']==27
    if tamper=='manifest':
        p=tmp_path/'manifest.json';v=json.loads(p.read_text());v['attempt']='1';p.write_text(json.dumps(v))
    elif tamper=='source':monkeypatch.setattr(c,'source_hashes',lambda head:{'source':'b'*64})
    else:
        p=tmp_path/('junit.xml' if tamper=='xml' else 'events.jsonl');p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError):c.receipt(tmp_path,HEAD,'12','2')


@pytest.mark.parametrize('tamper',['xml-text','duplicate-jsonl'])
def test_rehashed_semantic_tamper_refused(tmp_path,monkeypatch,tamper):
    import hashlib
    monkeypatch.setattr(c,'source_hashes',lambda head:{'source':'a'*64})
    for file,kind in [('model.json','MODEL_TESTS'),('native.json','HOSTED_FIXTURE_TESTS')]:
        (tmp_path/file).write_text(json.dumps(sample(kind)),encoding='utf-8')
    c.receipt(tmp_path,HEAD,'12','2',create=True)
    path=tmp_path/('junit.xml' if tamper=='xml-text' else 'events.jsonl')
    raw=path.read_text(encoding='utf-8')
    if tamper=='xml-text':raw=raw.replace(' />','>PHYSICAL_PASS</testcase>',1)
    else:raw=raw.replace('"outcome": "PASS"','"outcome": "FAIL", "outcome": "PASS"',1)
    path.write_text(raw,encoding='utf-8')
    p=tmp_path/'manifest.json';manifest=json.loads(p.read_text());manifest['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest();p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):c.receipt(tmp_path,HEAD,'12','2')
