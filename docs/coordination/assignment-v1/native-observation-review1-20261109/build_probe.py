"""Pure admission-only OBSERVATION data proposal; no authority/backend imports."""
import base64,copy,hashlib,json
from pathlib import Path
from jsonschema import Draft202012Validator
OUT=Path(__file__).resolve().parent
O=OUT/'originals'
def c(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(v):return hashlib.sha256(v).hexdigest()
def closed(props):return dict(type='object',properties=props,required=sorted(props),additionalProperties=False)
def const(v):return {'const':v}
def ref(name):return {'$ref':'#/$defs/'+name}
def dump(name,v):
    raw=json.dumps(v,indent=2,sort_keys=True).encode()+b'\n';(OUT/name).write_bytes(raw);return sha(raw)
old_raw=(O/'observation.schema.json').read_bytes()
assert sha(old_raw)=='736acca970bd392f46530cda94acd97701e879b18889c429a2c2113e04810e4c'
old=json.loads(old_raw)
defs=copy.deepcopy(old['$defs'])
defs['lab_observation']={k:copy.deepcopy(v) for k,v in old.items() if k not in ('$defs','$schema','$id')}
defs['binding']=closed(dict(cluster_id=ref('uuid4'),cluster_generation=ref('uuid4'),realm_id=ref('uuid4'),request_id=ref('uuid4'),idempotency_key=dict(type='string',pattern=r'^[A-Za-z0-9_-]{1,128}(?![\s\S])'),planned_job_id=ref('uuid4'),actor_principal_id=ref('uuid4'),quota_owner_id=dict(type='string',pattern=r'^[A-Za-z0-9_-]{1,128}(?![\s\S])'),target_request_sha256=ref('sha256'),target_request_schema_sha256=ref('sha256'),target_request_canonical_base64=dict(type='string',minLength=4,maxLength=21848,pattern=r'^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![\s\S])'),commissioned_profile_sha256=ref('sha256'),lab_submit_sha256=ref('sha256')))
props=dict(schema=const('unified.gateway.native-target-observation.v1-review1'),classification=const('OBSERVATION_DATA_ONLY_NOT_AUTHORITY'),disclosure=const('CURRENT_READ_AUTHORIZATION_REQUIRED_NOT_PROVEN_BY_JSON'),requested_operation=const('READ_RESEARCH'),original_binding=ref('binding'),snapshot_status={'enum':['CONSISTENT_NATIVE_SNAPSHOT','LAST_KNOWN_REFRESH_UNKNOWN','UNRESOLVED']},refresh_reason={'enum':['NONE','NO_QUORUM','TRANSPORT_UNKNOWN','INCOMPLETE_RECORDS','CLOCK_UNCERTAIN','BINDING_CORRUPTION','SOURCE_UNAVAILABLE']},native_observation=ref('lab_observation'),computation=closed(dict(status={'enum':['NO_COMPUTATION_EVIDENCE','METADATA_COMMITTED_PAYLOAD_NOT_INCLUDED']},payload=const(None),retrieval=const('NOT_ESTABLISHED'),scientific_payload_validation=const('NOT_PERFORMED_BY_THIS_ENVELOPE'))),publication=closed(dict(status=const('NOT_AUTHORIZED'),receipt=const(None),location=const(None))),projection=closed(dict(status=const('NOT_AVAILABLE'),receipt=const(None))),result_completion=const('NOT_ESTABLISHED'),commit_time_status=const('UNKNOWN_COMMIT_INSTANT'),permissions=closed({k:const(False) for k in ('dispatch','publish','retry','release_hold')}))
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:unified:gateway:native-target-observation:v1-review1','$defs':defs,**closed(props)}
def nested(field,requirements):return {'properties':{field:{'properties':requirements}}}
schema['allOf']=[
    {'if':{'properties':{'snapshot_status':const('UNRESOLVED')}},'then':nested('native_observation',{'state':const('UNKNOWN')}),'else':nested('native_observation',{'state':{'not':const('UNKNOWN')}})},
    {'if':{'properties':{'snapshot_status':const('LAST_KNOWN_REFRESH_UNKNOWN')}},'then':{'allOf':[nested('native_observation',{'policy_qualification':const('UNKNOWN'),'operation_observation':const('UNKNOWN')}),{'properties':{'refresh_reason':{'not':const('NONE')}}}]}},
    {'if':{'properties':{'snapshot_status':const('CONSISTENT_NATIVE_SNAPSHOT')}},'then':{'properties':{'refresh_reason':const('NONE')}}},
    {'if':{'properties':{'snapshot_status':const('UNRESOLVED')}},'then':{'properties':{'refresh_reason':{'not':const('NONE')}}}},
    {'if':nested('native_observation',{'computed':const(None)}),'then':nested('computation',{'status':const('NO_COMPUTATION_EVIDENCE')}),'else':nested('computation',{'status':const('METADATA_COMMITTED_PAYLOAD_NOT_INCLUDED')})},
]
Draft202012Validator.check_schema(schema)
schema_sha=dump('PROPOSED-native-observation.schema.json',schema)
validator=Draft202012Validator(schema)
def decode_wire_data(raw):
    # Proposed DATA codec guard, not a Root endpoint or native source verifier.
    assert type(raw) is bytes and 0<len(raw)<=16384
    depth=0;quoted=False;escaped=False
    for b in raw:
        if quoted:
            if escaped:escaped=False
            elif b==92:escaped=True
            elif b==34:quoted=False
        elif b==34:quoted=True
        elif b in (123,91):
            depth+=1;assert depth<=12
        elif b in (125,93):
            depth-=1;assert depth>=0
    assert depth==0 and not quoted
    def pairs(items):
        result={}
        for k,v in items:
            assert k not in result;result[k]=v
        return result
    def number(_):raise ValueError('JSON_NUMBER_NOT_NATIVE_METADATA')
    value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,parse_int=number,parse_float=number,parse_constant=number)
    assert c(value)==raw
    return value
T=(O/'SAMPLE-NOT-COMMISSIONED-native-outer.canonical.json').read_bytes()
P=(O/'SAMPLE-NOT-COMMISSIONED-profile.canonical.json').read_bytes()
L=(O/'SAMPLE-NOT-ISSUED-lab-submit.canonical.json').read_bytes()
t,p,l=map(json.loads,(T,P,L))
assert (sha(T),sha(P),sha(L))==('c0e6c331b6c307b83be6bee8add23b487612ff283d7167d4bb93114ec86d20b5','72d92e1ff023f00823b65637f3c79bc080510f8a02cfe24b3c4715286d43299c','b1675ccb47475d4d70788f3033cd9f05507ad320435d63d667d893aa07f00e71')
binding=dict(cluster_id=l['cluster_id'],cluster_generation=l['cluster_generation'],realm_id=p['realm_id'],request_id=l['request_id'],idempotency_key=l['idempotency_key'],planned_job_id=l['job_id'],actor_principal_id=l['original_actor_principal_id'],quota_owner_id=l['quota_owner_id'],target_request_sha256=sha(T),target_request_schema_sha256=sha((O/'PROPOSED-native-outer.schema.json').read_bytes()),target_request_canonical_base64=base64.b64encode(T).decode(),commissioned_profile_sha256=sha(P),lab_submit_sha256=sha(L))
def u(n):return '00000000-0000-4000-8000-'+str(n).zfill(12)
def receipt(n):return dict(receipt_id=u(n),modify_index=str(n),bytes_sha256=sha(('SAMPLE_NOT_NATIVE_RECEIPT_'+str(n)).encode()))
admission=receipt(20);dispatch=receipt(21);computed=receipt(22);cancel=receipt(23)
meta=dict(artifact_sha256='f4997d7d26211676cd8664e53d7999f8b71f203510f3b9a275b439c403e03940',artifact_bytes='2070',descriptor_sha256='664d34f06721b3d62404ea2f05b6b929a59b9e3eeecc281a71d2ca927c802cda',payload_durability='NOT_ESTABLISHED',publication='NOT_AUTHORIZED')
def native(phase,qualified=True,retained_computed=False):
    n=dict(schema='unified.authority.research-lab-observation.v1-review2',state=phase,job_id=l['job_id'],original_submit_request_id=l['request_id'],original_submit_intent_sha256=sha(L),assignment_id=u(30),execution_attempt_id=u(31),admission=copy.deepcopy(admission),computed=None,current=None,policy_qualification='CURRENT' if qualified else 'UNKNOWN',operation_observation='CONFIRMED' if qualified else 'UNKNOWN',publication='NOT_AUTHORIZED')
    if phase=='UNKNOWN':
        n.update(assignment_id=None,execution_attempt_id=None,admission=None,policy_qualification='UNKNOWN',operation_observation='UNKNOWN',reason='NATIVE_OUTCOME_UNKNOWN')
        return n
    kind,seq,r={'ADMITTED':('ADMISSION','1',admission),'RUNNING':('DISPATCH','2',dispatch),'COMPUTED':('COMPUTED_METADATA','3',computed),'CANCEL_REQUESTED':('CANCEL_REQUEST','4',cancel)}[phase]
    n['current']=dict(job_modify_index='40',sequence=seq,phase_kind=kind,phase_receipt=copy.deepcopy(r))
    if phase=='COMPUTED' or retained_computed:n['computed']=dict(metadata=copy.deepcopy(meta),receipt=copy.deepcopy(computed))
    return n
def envelope(n,snapshot='CONSISTENT_NATIVE_SNAPSHOT'):
    return dict(schema=props['schema']['const'],classification=props['classification']['const'],disclosure=props['disclosure']['const'],requested_operation='READ_RESEARCH',original_binding=copy.deepcopy(binding),snapshot_status=snapshot,refresh_reason='NONE' if snapshot=='CONSISTENT_NATIVE_SNAPSHOT' else 'TRANSPORT_UNKNOWN',native_observation=n,computation=dict(status='NO_COMPUTATION_EVIDENCE' if n['computed'] is None else 'METADATA_COMMITTED_PAYLOAD_NOT_INCLUDED',payload=None,retrieval='NOT_ESTABLISHED',scientific_payload_validation='NOT_PERFORMED_BY_THIS_ENVELOPE'),publication=dict(status='NOT_AUTHORIZED',receipt=None,location=None),projection=dict(status='NOT_AVAILABLE',receipt=None),result_completion='NOT_ESTABLISHED',commit_time_status='UNKNOWN_COMMIT_INSTANT',permissions={k:False for k in ('dispatch','publish','retry','release_hold')})
def require_data_joins(value):
    # Pure correlation against retained SAMPLE original. NEVER a live permit check.
    validator.validate(value)
    assert len(c(value))<=16384
    b=value['original_binding'];n=value['native_observation']
    assert c(b)==c(binding)
    raw=base64.b64decode(b['target_request_canonical_base64'],validate=True)
    assert base64.b64encode(raw).decode()==b['target_request_canonical_base64']
    assert raw==T and sha(raw)==b['target_request_sha256']
    assert (n['original_submit_request_id'],n['original_submit_intent_sha256'],n['job_id'])==(b['request_id'],b['lab_submit_sha256'],b['planned_job_id'])
    if n['state']=='ADMITTED':assert n['current']['phase_receipt']==n['admission']
    if n['state']=='COMPUTED':assert n['current']['phase_receipt']==n['computed']['receipt']
    if n['computed'] is not None:
        assert c(n['computed']['metadata'])==c(meta) # fixed target digests only, no payload revalidation claim
    return value
samples=[]
for phase in ('ADMITTED','RUNNING','COMPUTED','CANCEL_REQUESTED'):
    for qualified in (True,False):samples.append(envelope(native(phase,qualified)))
    samples.append(envelope(native(phase,False),'LAST_KNOWN_REFRESH_UNKNOWN'))
samples.append(envelope(native('UNKNOWN'),'UNRESOLVED'))
samples.append(envelope(native('CANCEL_REQUESTED',False,True),'LAST_KNOWN_REFRESH_UNKNOWN'))
structural_negatives=semantic_negatives=0
for index,s in enumerate(samples):
    require_data_joins(s)
    assert decode_wire_data(c(s))==s
    (OUT/('SAMPLE-DATA-NOT-NATIVE-'+str(index).zfill(2)+'.canonical.json')).write_bytes(c(s))
    for path,replacement in [(('result_completion',),'COMPLETED'),(('publication','status'),'COMMITTED'),(('projection','status'),'DURABLE'),(('permissions','dispatch'),True),(('permissions','publish'),True),(('permissions','retry'),True),(('permissions','release_hold'),True),(('computation','payload'),{'claimed_result':'NOT_ALLOWED'})]:
        bad=copy.deepcopy(s);target=bad
        for key in path[:-1]:target=target[key]
        target[path[-1]]=replacement
        assert list(validator.iter_errors(bad));structural_negatives+=1
    for field in binding:
        bad=copy.deepcopy(s)
        old_value=bad['original_binding'][field]
        if field=='target_request_canonical_base64':bad['original_binding'][field]=base64.b64encode(T+b' ').decode()
        elif field.endswith('sha256'):bad['original_binding'][field]='f'*64
        elif field in ('idempotency_key','quota_owner_id'):bad['original_binding'][field]='wrong_binding'
        else:bad['original_binding'][field]=u(99)
        assert bad['original_binding'][field]!=old_value
        try:require_data_joins(bad)
        except (AssertionError,ValueError):semantic_negatives+=1
        else:raise AssertionError(field)
# Schema valid but native original/phase correlation is not: DATA join controls.
for field,value in [('original_submit_request_id',u(99)),('original_submit_intent_sha256','f'*64),('job_id',u(99))]:
    bad=copy.deepcopy(samples[0]);bad['native_observation'][field]=value
    validator.validate(bad)
    try:require_data_joins(bad)
    except AssertionError:semantic_negatives+=1
    else:raise AssertionError(field)
bad=copy.deepcopy(samples[0]);bad['native_observation']['current']['phase_receipt']=receipt(99)
validator.validate(bad)
try:require_data_joins(bad)
except AssertionError:semantic_negatives+=1
else:raise AssertionError('phase receipt correlation')
# LAST_KNOWN is not CURRENT policy/operation; UNKNOWN has no receipt or execution grant.
bad=copy.deepcopy(samples[2]);bad['native_observation']['policy_qualification']='CURRENT';bad['native_observation']['operation_observation']='CONFIRMED'
assert list(validator.iter_errors(bad));structural_negatives+=1
bad=copy.deepcopy(samples[12]);bad['native_observation']['admission']=receipt(99)
assert list(validator.iter_errors(bad));structural_negatives+=1
for operation in ('SUBMIT_RESEARCH','CANCEL_OWN_JOB'):
    bad=copy.deepcopy(samples[0]);bad['requested_operation']=operation
    assert list(validator.iter_errors(bad));structural_negatives+=1
wire=c(samples[0]);raw_negatives=[wire+b'\n',wire[:-1]+b',"schema":"duplicate"}',b' '*16385,b'{"x":'+b'['*13+b'0'+b']'*13+b'}',b'{"x":1}',b'{"x":1.0}',b'{"x":NaN}',b'{"x":"\xff"}']
for raw in raw_negatives:
    try:decode_wire_data(raw)
    except (AssertionError,ValueError):pass
    else:raise AssertionError('raw codec negative')
report=dict(scope='PURE_ADMISSION_ONLY_OBSERVATION_DATA_CONTRACT_NOT_AUTHORITY',schema_sha256=schema_sha,source_lab_observation_sha256=sha(old_raw),structural_positive_samples=len(samples),structural_negative_vectors=structural_negatives,pure_semantic_correlation_negative_vectors=semantic_negatives,raw_codec_negative_vectors=len(raw_negatives),max_sample_encoded_bytes=max(len(c(x)) for x in samples),publication_profile='FIXED_NOT_AUTHORIZED_NO_COMMITTED_BRANCH',projection_profile='FIXED_NOT_AVAILABLE_NO_DURABLE_BRANCH',completion_profile='FIXED_NOT_ESTABLISHED_NO_COMPLETED_BRANCH',known_facts_preserved_when_policy_unknown=True,actual_consul_calls=0,broker_contexts=0,issued_assignments=0,target_calls=0,scheduler_dispatches=0,shared_wire_abi_approved=False,go_no_go='DESIGN_PENDING_NO_GO')
dump('pure-verification.json',report)
print(json.dumps(report,indent=2))
