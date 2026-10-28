import json,pytest
from s0_smoke.evidence import verify_chain
from s0_smoke.storage import Journal
CTX=dict(head='a'*40,run_id='11111111-1111-4111-8111-111111111111',role='PC4')
def sample(tmp_path):
 with Journal(tmp_path,'events.jsonl',CTX) as j:j.add('started',{});j.add('finished',{})
 return (tmp_path/'events.jsonl').read_bytes()
def test_exact_chain(tmp_path):assert len(verify_chain(sample(tmp_path),CTX))==2
@pytest.mark.parametrize('kind',['byte','head','sequence','truncate','duplicate','missing'])
def test_forged_or_interrupted_evidence(tmp_path,kind):
 b=sample(tmp_path)
 if kind=='byte':b=b.replace(b'started',b'changed')
 elif kind=='head':b=b.replace(b'a'*40,b'b'*40)
 elif kind=='sequence':b=b.replace(b'"seq":2',b'"seq":3')
 elif kind=='truncate':b=b[:-1]
 elif kind=='duplicate':b+=b.splitlines(keepends=True)[-1]
 else:b=b.splitlines(keepends=True)[-1]
 with pytest.raises(ValueError):verify_chain(b,CTX)


def failed_fixture(tmp_path):
 from s0_smoke.cli import finish
 from s0_smoke.storage import write_new
 write_new(tmp_path,'claim.json',b'{"fixture":true}')
 with Journal(tmp_path,'events.jsonl',CTX) as j:
  j.add('started',{});j.add('blocked',{'error_class':'ValueError'});j.add('finished',{'result':{},'error':'ValueError'})
 with Journal(tmp_path,'market.jsonl',CTX):pass
 finish(tmp_path,{'plan':{'head':CTX['head'],'run_id':CTX['run_id']},'role':'PC4'},{},'ValueError',{'tree':'b'*40},'c'*64)

def test_failed_empty_feed_evidence_is_exportable_without_keys(tmp_path):
 import zipfile
 from s0_smoke.evidence import archive_evidence
 failed_fixture(tmp_path);(tmp_path/'tls-key.pem').write_bytes(b'SYNTHETIC_NEVER_EXPORT')
 r=archive_evidence(tmp_path,CTX,'c'*64);assert r['observation']=='BLOCKED_OR_PARTIAL'
 with zipfile.ZipFile(tmp_path/'s0-evidence.zip') as z:assert 'tls-key.pem' not in z.namelist()

def test_rebound_secret_index_still_refused(tmp_path):
 from s0_smoke.evidence import verify_evidence
 failed_fixture(tmp_path);p=tmp_path/'sha256.json';v=json.loads(p.read_text());v['files']['tls-key.pem']='a'*64;p.write_text(json.dumps(v))
 with pytest.raises(ValueError):verify_evidence(tmp_path,CTX,'c'*64)

@pytest.mark.parametrize('field',['head','run_id','attempt','tree'])
def test_ci_receipt_rejects_cross_run_or_tree_substitution(field):
 from tools.verify_s0_artifacts_ci import require_context
 expected=dict(head='a'*40,run_id='123',attempt='2',tree='b'*40)
 require_context(dict(expected),expected)
 wrong=dict(expected);wrong[field]='stale'
 with pytest.raises(RuntimeError):require_context(wrong,expected)
 wrong=dict(expected);del wrong[field]
 with pytest.raises(RuntimeError):require_context(wrong,expected)
