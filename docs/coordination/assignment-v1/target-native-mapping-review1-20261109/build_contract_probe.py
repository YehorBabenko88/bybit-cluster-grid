"""Pure data/schema/hash probe. ZERO target/Consul/broker/scheduler operations."""
import base64,copy,hashlib,json,re
from pathlib import Path
from jsonschema import Draft202012Validator
OUT=Path(__file__).resolve().parent
ORIGINAL=OUT/'originals'
def c(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(v):return hashlib.sha256(v).hexdigest()
def save(name,v):
    raw=json.dumps(v,indent=2,sort_keys=True).encode()+b'\n';(OUT/name).write_bytes(raw);return sha(raw)
def closed(props):return dict(type='object',properties=props,required=sorted(props),additionalProperties=False)
def const(value):return {'const':value}
old_raw=(ORIGINAL/'target-direct-request.schema.json').read_bytes()
assert sha(old_raw)=='2a7a9370eedc43b76b03fa13252e86606162ae8f494a362fd69d5b22a85858fe'
lab_raw=(ORIGINAL/'lab-submit-review1.schema.json').read_bytes()
assert sha(lab_raw)=='19357891fc022a87831009f17c663304ab72d88ed6ea344bb65c6bc325a321cc'
old=json.loads(old_raw);lab_schema=json.loads(lab_raw)
native=copy.deepcopy(old);native['$id']='urn:unified:gateway:target-native-request:v1-review1'
p=native['properties'];p['schema']=const('unified.gateway.target-native-request.v1-review1')
p['execution_mode']=const('NATIVE_RESEARCH_ADMISSION_REQUEST_NOT_PERMISSION')
p['quota_owner']=dict(type='string',pattern=r'^[A-Za-z0-9_-]{1,128}(?![\s\S])')
for name in ('principal_id','authority_generation'):p[name]=copy.deepcopy(old['properties']['request_id'])
p['result_schema']=const('unified.gateway.native-target-observation.v1-review1')
# Pre-issuance request assignment/fence and result-ref remain null, never grants.
ns=save('PROPOSED-native-outer.schema.json',native)
sample={name:value.get('const') for name,value in old['properties'].items()}
sample.update(request_id='00000000-0000-4000-8000-000000000011',idempotency_key='fixed-btc-three-row-1',resource_budget={k:v['const'] for k,v in old['properties']['resource_budget']['properties'].items()})
direct=copy.deepcopy(sample)
sample.update(schema=p['schema']['const'],execution_mode=p['execution_mode']['const'],quota_owner='lab_quota',principal_id='00000000-0000-4000-8000-000000000004',authority_generation='00000000-0000-4000-8000-000000000002',result_schema=p['result_schema']['const'])
v=Draft202012Validator(native);v.check_schema(native);v.validate(sample)
assert len(sample)==20 and len(lab_schema['required'])==13
assert list(v.iter_errors(direct)) # no silent direct-profile upgrade
outer=c(sample);outer_sha=sha(outer)
# This profile is SAMPLE DATA ONLY. No actual actor/cert/commissioning or grant.
profile=dict(schema='unified.authority.target-bound-research-profile.v2-review1',cluster_id='00000000-0000-4000-8000-000000000001',realm_id='00000000-0000-4000-8000-000000000003',principal_registry={'a'*64:sample['principal_id']},input_request_sha256=sample['parameters_digest'],producer_head='aed8a7c8a952f96803c207d5e90b133969a47f04',resources=dict(cpu_millicores='1000',resident_memory_bytes='268435456',max_artifact_bytes='1048576'),expiry_semantics='NATIVE_SESSION_INVALIDATION_NOT_UTC_AT_COMMIT',expires_utc='2026-11-09T16:00:00Z',target_binding=dict(target_request_schema_sha256=ns,target_request_canonical_base64=base64.b64encode(outer).decode(),target_request_sha256=outer_sha,request_id=sample['request_id'],job_id='00000000-0000-4000-8000-000000000010',idempotency_key=sample['idempotency_key'],cluster_generation=sample['authority_generation'],actor_principal_id=sample['principal_id'],quota_owner_id=sample['quota_owner'],producer_request_sha256=sample['parameters_digest'],producer_head='aed8a7c8a952f96803c207d5e90b133969a47f04'))
profile_raw=c(profile);profile_sha=sha(profile_raw)
profile_schema_raw=(ORIGINAL/'broker-profile-v1.schema.json').read_bytes()
assert sha(profile_schema_raw)=='e999dc35c4737346ac152172292078ac9eed040ffdf31afdf001ae86974f51d1'
profile_schema=json.loads(profile_schema_raw)
profile_schema['$id']='urn:unified:target-bound-research-profile:v2-review1'
profile_schema['properties']['schema']=const(profile['schema'])
binding_props={}
for key in profile['target_binding']:
    if key.endswith('sha256'):binding_props[key]={'$ref':'#/$defs/sha256'}
    elif key in ('request_id','job_id','cluster_generation','actor_principal_id'):binding_props[key]={'$ref':'#/$defs/uuid4'}
    elif key=='producer_head':binding_props[key]=const(profile['producer_head'])
    elif key=='target_request_canonical_base64':binding_props[key]=dict(type='string',minLength=4,maxLength=21848,pattern=r'^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![\s\S])')
    else:binding_props[key]=dict(type='string',pattern=r'^[A-Za-z0-9_-]{1,128}(?![\s\S])')
profile_schema['properties']['target_binding']=closed(binding_props)
profile_schema['required']=sorted(profile_schema['required']+['target_binding'])
Draft202012Validator.check_schema(profile_schema);Draft202012Validator(profile_schema).validate(profile)
ps=save('PROPOSED-commissioned-profile-v2.schema.json',profile_schema)
assert len(profile_raw)<=16384
lab=dict(schema='unified.gateway.lab-job-submit.v1-review1',operation='SUBMIT_RESEARCH',cluster_id=profile['cluster_id'],cluster_generation=sample['authority_generation'],request_id=sample['request_id'],job_id=profile['target_binding']['job_id'],original_actor_principal_id=sample['principal_id'],quota_owner_id=sample['quota_owner'],idempotency_key=sample['idempotency_key'],commissioned_profile_sha256=profile_sha,input_request_sha256=profile['input_request_sha256'],producer_head=profile['producer_head'],resources=copy.deepcopy(profile['resources']))
Draft202012Validator(lab_schema).validate(lab)
assert base64.b64decode(profile['target_binding']['target_request_canonical_base64'],validate=True)==outer
assert json.loads(outer)==sample and sha(outer)==profile['target_binding']['target_request_sha256']
assert lab['commissioned_profile_sha256']==sha(profile_raw)
# Canonical comparison, not Python numeric ==, preserves exact preflight types.
assert c(sample['resource_budget'])==c(direct['resource_budget'])
sensitivity=[]
for field in sample:
    changed=copy.deepcopy(sample);changed[field]={'CHANGED_ONE_FIELD_NOT_AN_ADMISSION_VECTOR':field}
    changed_raw=c(changed);assert sha(changed_raw)!=outer_sha
    changed_profile=copy.deepcopy(profile);changed_profile['target_binding'].update(target_request_canonical_base64=base64.b64encode(changed_raw).decode(),target_request_sha256=sha(changed_raw))
    changed_lab=copy.deepcopy(lab);changed_lab['commissioned_profile_sha256']=sha(c(changed_profile))
    assert sha(c(changed_lab))!=sha(c(lab))
    sensitivity.append(field)
negatives=[]
for field in sample:
    bad=copy.deepcopy(sample);del bad[field];assert list(v.iter_errors(bad));negatives.append('missing:'+field)
bad=copy.deepcopy(sample);bad['unowned_extra']=True;assert list(v.iter_errors(bad));negatives.append('extra')
# ROOT allows dot, frozen lab rejects dot. Do not rekey/hash/normalize it.
bad=copy.deepcopy(sample);bad['idempotency_key']='request.with.dot';v.validate(bad)
bad_lab=copy.deepcopy(lab);bad_lab['idempotency_key']=bad['idempotency_key']
assert list(Draft202012Validator(lab_schema).iter_errors(bad_lab));negatives.append('dot_idempotency_unrepresentable')
for name in ('assignment_revision','fencing_token','result_artifact_ref'):
    bad=copy.deepcopy(sample);bad[name]='claimed-grant';assert list(v.iter_errors(bad));negatives.append('nonnull:'+name)
error_codes=['DIRECT_PROFILE_NOT_ADMISSIBLE','PROFILE_NOT_COMMISSIONED','MAPPING_NOT_REPRESENTABLE','TARGET_BINDING_MISMATCH','IDENTITY_SCOPE_DENIED','INPUT_BINDING_NOT_ADMITTED','RESOURCE_QUOTA_NOT_QUALIFIED','WORKER_LEASE_FENCE_NOT_QUALIFIED','UTC_AT_COMMIT_NOT_QUALIFIED','PUBLICATION_NOT_QUALIFIED','IDEMPOTENCY_CONFLICT','CONSENSUS_UNAVAILABLE','NATIVE_OUTCOME_UNKNOWN']
nullable_sha={'anyOf':[dict(type='null'),dict(type='string',pattern=r'^[0-9a-f]{64}(?![\s\S])')]}
error=closed(dict(schema=const('unified.authority.target-admission-error.v1-review1'),code={'enum':error_codes},request_id={'anyOf':[dict(type='null'),copy.deepcopy(old['properties']['request_id'])]},target_request_sha256=nullable_sha,lab_submit_sha256=nullable_sha,this_attempt={'enum':['NOT_ATTEMPTED_THIS_CALL','THIS_ATTEMPT_ROLLED_BACK','UNCERTAIN']},native_original_state={'enum':['UNKNOWN','ADMITTED','RUNNING','COMPUTED','CANCEL_REQUESTED']},execution_permitted=const(False),retry_permitted=const(False),hold_release_permitted=const(False)))
error.update({'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:unified:target-admission-error:v1-review1'})
Draft202012Validator.check_schema(error);save('PROPOSED-admission-error.schema.json',error)
for code in error_codes:
    Draft202012Validator(error).validate(dict(schema=error['properties']['schema']['const'],code=code,request_id=sample['request_id'],target_request_sha256=outer_sha,lab_submit_sha256=sha(c(lab)),this_attempt='UNCERTAIN' if code=='NATIVE_OUTCOME_UNKNOWN' else 'NOT_ATTEMPTED_THIS_CALL',native_original_state='UNKNOWN',execution_permitted=False,retry_permitted=False,hold_release_permitted=False))
(OUT/'SAMPLE-NOT-COMMISSIONED-native-outer.canonical.json').write_bytes(outer)
(OUT/'SAMPLE-NOT-COMMISSIONED-profile.canonical.json').write_bytes(profile_raw)
(OUT/'SAMPLE-NOT-ISSUED-lab-submit.canonical.json').write_bytes(c(lab))
assert sha((OUT/'SAMPLE-NOT-COMMISSIONED-native-outer.canonical.json').read_bytes())==outer_sha
assert sha((OUT/'SAMPLE-NOT-COMMISSIONED-profile.canonical.json').read_bytes())==profile_sha
assert sha((OUT/'SAMPLE-NOT-ISSUED-lab-submit.canonical.json').read_bytes())==sha(c(lab))
report=dict(scope='PURE_CONTRACT_DATA_ONLY_ZERO_AUTHORITY_OR_TARGET_CALLS',original_direct_schema_sha256=sha(old_raw),unchanged_lab_schema_sha256=sha(lab_raw),proposed_native_outer_schema_sha256=ns,proposed_profile_schema_sha256=ps,sample_outer_sha256=outer_sha,sample_profile_sha256=profile_sha,sample_profile_bytes=len(profile_raw),sample_lab_intent_sha256=sha(c(lab)),outer_fields=20,lab_fields=13,direct_profile_rejected=True,byte_binding_sensitivity_fields=sensitivity,byte_binding_sensitivity_note='20_ONE_FIELD_MUTATIONS_ARE_HASH_ALGEBRA_NOT_VALID_ADMISSION_OR_NATIVE_TESTS',structural_negative_cases=negatives,error_code_structural_positives=len(error_codes),actual_consul_calls=0,broker_contexts=0,issued_assignments=0,target_calls=0,scheduler_dispatches=0,new_wire_abi_approved=False,go_no_go='DESIGN_PENDING_NO_GO')
save('pure-contract-verification.json',report)
print(json.dumps(report,indent=2))
