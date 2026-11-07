"""Native identifier correction ONLY; no caller ID relaxation/native mutation."""
import copy,hashlib,json,re,uuid
from pathlib import Path
from jsonschema import Draft202012Validator

OUT=Path(__file__).resolve().parent
old_path=OUT.parent/'RESEARCH-LAB-ADMISSION-REVIEW2'/'lease-lock.schema.json'
old_raw=old_path.read_bytes()
assert hashlib.sha256(old_raw).hexdigest()=='50da8f3276772709b623c7c2629f257caa19da80221b21d81db7bc1c8a95b36b'
old=json.loads(old_raw);new=copy.deepcopy(old)
new['$id']='urn:unified:research-lab:lease-lock:v1-review3'
new['properties']['schema']['const']='unified.authority.research-lab-lease.v1-review3'
new['$defs']['native_session_id']=dict(type='string',minLength=36,maxLength=36,
    pattern=r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![\s\S])')
new['properties']['worker_session_id']={'$ref':'#/$defs/native_session_id'}
evidence_path=Path('C:/Users/LS-5/Documents/Codex/2026-11-06/codex-agent-2-high-availability-distributed/work/research-broker-native-evidence-6/actual-native-session.json')
evidence_raw=evidence_path.read_bytes();evidence=json.loads(evidence_raw)
sid=evidence['source_session_id']
assert evidence['exact_join'] and evidence['session_create_response']['status']==200
assert json.loads(evidence['session_create_response']['raw'])['ID']==sid==evidence['native_lock']['session']
assert sid==str(uuid.UUID(sid)) and uuid.UUID(sid).version!=4
assert evidence['binary_version']=='Consul v1.22.2'
assert evidence['binary_sha256']=='41762ef5b98c8dd9b6852df6cfbceed37e7f0acc5760856be33100f1092475e1'
base=dict(schema='unified.authority.research-lab-lease.v1-review2',realm_id='11111111-1111-4111-8111-111111111111',
    lease_id='22222222-2222-4222-8222-222222222222',assignment_id='33333333-3333-4333-8333-333333333333',
    execution_attempt_id='44444444-4444-4444-8444-444444444444',worker_session_id=sid)
assert not Draft202012Validator(old).is_valid(base)
sample=dict(base,schema='unified.authority.research-lab-lease.v1-review3')
Draft202012Validator.check_schema(new);validator=Draft202012Validator(new);validator.validate(sample)
invalid=[None,True,'arbitrary',sid.upper(),sid+'\n',sid+'x',sid.replace('-',''),sid[:-1]]
for item in invalid:
    assert not validator.is_valid(dict(sample,worker_session_id=item))
# Client/lease/assignment/attempt remain strict UUIDv4; changing any to native ID denies.
for field in ('realm_id','lease_id','assignment_id','execution_attempt_id'):
    assert not validator.is_valid(dict(sample,**{field:sid}))
def diff(a,b,path=''):
    if type(a) is dict and type(b) is dict:
        result=[]
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b: result.append(path+'/'+key)
            else: result+=diff(a[key],b[key],path+'/'+key)
        return result
    return [] if a==b else [path]
delta=diff(old,new)
assert set(delta)=={'/$id','/$defs/native_session_id','/properties/schema/const','/properties/worker_session_id/$ref'}
new_raw=json.dumps(new,sort_keys=True,separators=(',',':')).encode()+b'\n'
(OUT/'lease-lock.schema.json').write_bytes(new_raw)
(OUT/'actual-native-session.json').write_bytes(evidence_raw)
report=dict(scope='NATIVE_SESSION_ID_FORMAT_CORRECTION_NOT_SYNTAX_AS_AUTHORITY',
    previous_sha256=hashlib.sha256(old_raw).hexdigest(),successor_sha256=hashlib.sha256(new_raw).hexdigest(),
    evidence_sha256=hashlib.sha256(evidence_raw).hexdigest(),exact_delta=delta,
    actual_native_old_schema_rejected=True,actual_native_new_schema_accepted=True,
    malformed_noncanonical_negatives=len(invalid),unchanged_client_uuid4_negatives=4,
    actual_foreign_stale_native_tests='OWNER_BROKER_LOG_NATIVE6_SEPARATE_NOT_SCHEMA_VECTORS',
    actual_native_mutations_in_this_generator=0)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
