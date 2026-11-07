"""Strict candidate schema/vector generation ONLY; no native issuer or calls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from jsonschema import Draft202012Validator

OUT=Path(__file__).resolve().parent
STRICT=Path('C:/Users/LS-5/Documents/Codex/2026-11-06/codex-agent-4-distributed-storage-integrity/outputs/storage-publication-intent-review2/publication-intent.schema.json')
raw=STRICT.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='b9e3643751b1ff184dc6f0813b090159c23d37215e0afcd8829070d5fe593406'
base=json.loads(raw)['$defs']
defs={k:copy.deepcopy(base[k]) for k in ('uuid4','sha256','id','u63','positive')}
def ref(name): return {'$ref':'#/$defs/'+name}
def closed(props): return dict(type='object',properties=props,required=sorted(props),additionalProperties=False)
def const(value): return {'const':value}
def optional(part): return {'oneOf':[part,{'type':'null'}]}
def enum(*values): return {'enum':list(values)}
def schema(name,body,definitions=None):
    return {'$schema':'https://json-schema.org/draft/2020-12/schema',
        '$id':'urn:unified:research-lab:'+name+':v1-review2',
        '$defs':copy.deepcopy(defs if definitions is None else definitions),**body}
def encode(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
defs['resources']=closed({k:ref('u63') for k in ('cpu_millicores','resident_memory_bytes','max_artifact_bytes')})
defs['demand']=closed({k:ref('positive') for k in ('cpu_millicores','resident_memory_bytes','max_artifact_bytes')})
defs['receipt_observation']=closed(dict(receipt_id=ref('uuid4'),modify_index=ref('positive'),bytes_sha256=ref('sha256')))
defs['artifact_metadata']=closed(dict(artifact_sha256=ref('sha256'),artifact_bytes=ref('positive'),
    descriptor_sha256=ref('sha256'),payload_durability=const('NOT_ESTABLISHED'),publication=const('NOT_AUTHORIZED')))
defs['computed_observation']=closed(dict(metadata=ref('artifact_metadata'),receipt=ref('receipt_observation')))
assignment=closed(dict(schema=const('unified.authority.research-lab-assignment.v1-review2'),
    cluster_generation=ref('uuid4'),realm_id=ref('uuid4'),job_id=ref('uuid4'),request_id=ref('uuid4'),
    original_intent_sha256=ref('sha256'),assignment_id=ref('uuid4'),assignment_revision=ref('positive'),
    lease_id=ref('uuid4'),lease_epoch=ref('positive'),grant_revision=ref('positive'),leader_lock_index=ref('positive'),
    node_id=ref('uuid4'),worker_incarnation_id=ref('uuid4'),execution_attempt_id=ref('uuid4'),owner_id=ref('uuid4'),
    quota_owner_id=ref('id'),resources=ref('demand'),profile_sha256=ref('sha256')))
counter=closed(dict(schema=const('unified.authority.research-lab-counter.v1-review2'),realm_id=ref('uuid4'),
    worker_id=ref('uuid4'),revision=ref('u63'),previous_revision=optional(ref('u63'))))
ledger=closed(dict(schema=const('unified.authority.research-lab-resource-ledger.v1-review2'),realm_id=ref('uuid4'),
    worker_id=ref('uuid4'),incarnation_id=ref('uuid4'),revision=ref('u63'),previous_revision=optional(ref('u63')),
    active_jobs=ref('u63'),uncertain_jobs=ref('u63'),held=ref('resources'),uncertain=ref('resources')))
quota=closed(dict(schema=const('unified.authority.research-lab-quota-ledger.v1-review2'),realm_id=ref('uuid4'),
    quota_owner_id=ref('id'),revision=ref('u63'),previous_revision=optional(ref('u63')),
    active_jobs=ref('u63'),uncertain_jobs=ref('u63')))
hold=closed(dict(schema=const('unified.authority.research-lab-hold.v1-review2'),realm_id=ref('uuid4'),
    assignment_id=ref('uuid4'),job_id=ref('uuid4'),state=const('HELD'),resources=ref('demand')))
lease=closed(dict(schema=const('unified.authority.research-lab-lease.v1-review2'),realm_id=ref('uuid4'),
    lease_id=ref('uuid4'),assignment_id=ref('uuid4'),execution_attempt_id=ref('uuid4'),worker_session_id=ref('uuid4')))
submit_raw=subprocess.check_output(['git','--no-replace-objects','-C',
    'C:/Users/LS-5/.codex/worktrees/agent5-gateway-jobs/unified-system','show',
    '2693c68f3e96ddf744a3c87ea8fb3ddd80c0155e:docs/intelligence/jobs/lab-submit-review1.schema.json'])
assert hashlib.sha256(submit_raw).hexdigest()=='19357891fc022a87831009f17c663304ab72d88ed6ea344bb65c6bc325a321cc'
cancel_raw=(OUT.parent/'RESEARCH-LAB-ADMISSION-REVIEW1'/'cancel.schema.canonical.json').read_bytes()
assert hashlib.sha256(cancel_raw).hexdigest()=='38069175d528de2f04e59a1f13896ed67e17bbad2e651de4e6fa2a2ee4fa0c55'
request_branches=[{k:v for k,v in json.loads(b).items() if k not in ('$id','$schema')} for b in (submit_raw,cancel_raw)]
command=closed(dict(schema=const('unified.authority.research-lab-command.v1-review2'),intent={'oneOf':request_branches}))
states={'ADMITTED':'ADMISSION','RUNNING':'DISPATCH','COMPUTED':'COMPUTED_METADATA','CANCEL_REQUESTED':'CANCEL_REQUEST'}
job_branches=[]
for state,kind in states.items():
    job_branches.append(closed(dict(schema=const('unified.authority.research-lab-job.v1-review2'),
        job_id=ref('uuid4'),sequence=ref('positive'),previous_sequence=ref('u63'),state=const(state),
        original_request_id=ref('uuid4'),original_intent_sha256=ref('sha256'),assignment_id=ref('uuid4'),
        admission_receipt_id=ref('uuid4'),dispatch_event_id=ref('uuid4'),computed_event_id=ref('uuid4'),
        phase_kind=const(kind),phase_ref=ref('uuid4'),publication=const('NOT_AUTHORIZED'))))
phase_branches=[]
for kind in states.values():
    phase_branches.append(closed(dict(schema=const('unified.authority.research-lab-phase-receipt.v1-review2'),
        kind=const(kind),event_id=ref('uuid4'),source_request_id=ref('uuid4'),source_intent_sha256=ref('sha256'),
        original_submit_request_id=ref('uuid4'),original_submit_intent_sha256=ref('sha256'),
        job_id=ref('uuid4'),assignment_id=ref('uuid4'),execution_attempt_id=ref('uuid4'),job_sequence=ref('positive'),
        artifact_metadata=ref('artifact_metadata') if kind=='COMPUTED_METADATA' else {'type':'null'},
        committed_at_utc=const(None),commit_time_status=const('UNKNOWN_COMMIT_INSTANT'))))
observation_branches=[]
for state,kind in states.items():
    if state=='COMPUTED': computed=ref('computed_observation')
    elif state=='CANCEL_REQUESTED': computed=optional(ref('computed_observation'))
    else: computed={'type':'null'}
    properties=dict(schema=const('unified.authority.research-lab-observation.v1-review2'),
        original_submit_request_id=ref('uuid4'),original_submit_intent_sha256=ref('sha256'),job_id=ref('uuid4'),
        state=const(state),assignment_id=ref('uuid4'),execution_attempt_id=ref('uuid4'),
        admission=ref('receipt_observation'),current=closed(dict(sequence=ref('positive'),
            job_modify_index=ref('positive'),phase_kind=const(kind),phase_receipt=ref('receipt_observation'))),
        computed=computed,publication=const('NOT_AUTHORIZED'))
    for qualification in ('CURRENT','UNKNOWN'):
        observation_branches.append(closed(dict(properties,policy_qualification=const(qualification),
            operation_observation=const('CONFIRMED' if qualification=='CURRENT' else 'UNKNOWN'))))
observation_branches.append(closed(dict(schema=const('unified.authority.research-lab-observation.v1-review2'),
    original_submit_request_id=ref('uuid4'),original_submit_intent_sha256=ref('sha256'),job_id=ref('uuid4'),state=const('UNKNOWN'),
    assignment_id=const(None),execution_attempt_id=const(None),admission=const(None),current=const(None),computed=const(None),
    publication=const('NOT_AUTHORIZED'),reason=enum('NATIVE_OUTCOME_UNKNOWN','NO_QUORUM',
        'INCOMPLETE_DURABLE_PAIR','UNSUPPORTED_PROFILE','BINDING_CORRUPTION'),
    policy_qualification=const('UNKNOWN'),operation_observation=const('UNKNOWN'))))
error_branches=[]
for code,attempt_state in (
    ('INVALID_REQUEST','NOT_ATTEMPTED'),('AUTHORIZATION_DENIED','NOT_ATTEMPTED'),
    ('PROFILE_UNAVAILABLE','NOT_ATTEMPTED'),('RESOURCE_UNAVAILABLE','NOT_ATTEMPTED'),
    ('ORIGINAL_BINDING_CONFLICT','NOT_ATTEMPTED'),('NATIVE_PLAN_LIMIT','NOT_ATTEMPTED'),
    ('PRECONDITION_CONFLICT','THIS_ATTEMPT_ROLLED_BACK'),('NATIVE_OUTCOME_UNKNOWN','UNCERTAIN'),
    ('NO_QUORUM','UNCERTAIN'),('POLICY_QUALIFICATION_UNKNOWN','UNCERTAIN')):
    error_branches.append(closed(dict(schema=const('unified.authority.research-lab-error.v1-review2'),code=const(code),
        attempt_state=const(attempt_state),original_submit_request_id=optional(ref('uuid4')),
        original_submit_intent_sha256=optional(ref('sha256')),job_id=optional(ref('uuid4')),
        original_operation_absence_proven=const(False),retry_with_new_identity=const(False))))
schemas={'issued-assignment':schema('issued-assignment',assignment),
    'assignment-counter':schema('assignment-counter',counter),'resource-ledger':schema('resource-ledger',ledger),
    'quota-ledger':schema('quota-ledger',quota),'resource-hold':schema('resource-hold',hold),
    'lease-lock':schema('lease-lock',lease),'original-command':schema('original-command',command),
    'job-state':schema('job-state',{'oneOf':job_branches}),
    'phase-receipt':schema('phase-receipt',{'oneOf':phase_branches}),
    'observation':schema('observation',{'oneOf':observation_branches}),
    'error':schema('error',{'oneOf':error_branches})}
def example(part,definitions):
    if '$ref' in part: return example(definitions[part['$ref'].split('/')[-1]],definitions)
    if 'const' in part: return part['const']
    if 'enum' in part: return part['enum'][0]
    if 'oneOf' in part: return example(part['oneOf'][0],definitions)
    if 'allOf' in part: return '1'
    if part.get('type')=='object': return {k:example(v,definitions) for k,v in part['properties'].items()}
    if part.get('type')=='null': return None
    pattern=part.get('pattern','')
    if '[0-9a-f]{8}' in pattern: return '11111111-1111-4111-8111-111111111111'
    if '[0-9a-f]{64}' in pattern: return 'a'*64
    if 'A-Za-z0-9' in pattern: return 'test-id'
    return '1'
def leaves(value,path=()):
    if type(value) is dict:
        for k,v in value.items(): yield from leaves(v,path+(k,))
    elif type(value) is str: yield path,value
def change(value,path,replacement):
    cursor=value
    for k in path[:-1]: cursor=cursor[k]
    cursor[path[-1]]=replacement
summary=[]
for name,value in schemas.items():
    Draft202012Validator.check_schema(value)
    validator=Draft202012Validator(value)
    branches=value.get('oneOf',[value])
    positives=negatives=0
    for branch in branches:
        sample=example(branch,value['$defs'])
        validator.validate(sample); positives+=1
        for path,item in leaves(sample):
            mutated=copy.deepcopy(sample);change(mutated,path,item+'\n')
            assert not validator.is_valid(mutated),(name,path,'LF')
            negatives+=1
            if item=='1':
                mutated=copy.deepcopy(sample);change(mutated,path,'9223372036854775808')
                assert not validator.is_valid(mutated),(name,path,'overflow')
                negatives+=1
        mutated=dict(sample,admitted=True)
        assert not validator.is_valid(mutated);negatives+=1
        for key in sample:
            mutated=copy.deepcopy(sample);del mutated[key]
            assert not validator.is_valid(mutated),(name,key,'missing')
            negatives+=1
    payload=encode(value)+b'\n'
    (OUT/(name+'.schema.json')).write_bytes(payload)
    summary.append(dict(name=name,sha256=hashlib.sha256(payload).hexdigest(),positives=positives,negatives=negatives))
# Arithmetic is semantic, never inferred from structural schema success.
def successor(old,new): return type(old) is int and type(new) is int and 0<=old<2**63-1 and new==old+1
arithmetic=[(0,1,True),(7,8,True),(7,1,False),(7,7,False),(7,9,False),(2**63-1,0,False),(2**63-1,2**63,False)]
assert all(successor(a,b)==expected for a,b,expected in arithmetic)
report=dict(scope='STRUCTURAL_DATA_AND_ARITHMETIC_VECTORS_ONLY_NOT_NATIVE_ADMISSION',schemas=summary,
    positives=sum(s['positives'] for s in summary),negatives=sum(s['negatives'] for s in summary),
    arithmetic_controls=len(arithmetic),all_pass=True,actual_consul_requests=0)
(OUT/'structural-validation.json').write_bytes(encode(report)+b'\n')
print(json.dumps(report,indent=2))
