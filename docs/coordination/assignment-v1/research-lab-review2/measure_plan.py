"""Review2 exact candidate plan serialization, zero Consul or broker calls."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from jsonschema import Draft202012Validator

OUT=Path(__file__).resolve().parent
OLD=OUT.parent/'RESEARCH-LAB-ADMISSION-REVIEW1'
baseline=json.loads((OLD/'measurement.json').read_bytes())
assert hashlib.sha256((OLD/'measurement.json').read_bytes()).hexdigest()=='1fb6365a57a2206349dd3ac0499d54a7d22be0f7a1e1ec97544ba07342cb219e'
grid='C:/Users/LS-5/Documents/Codex/2026-11-06/codex-agent-2-high-availability-distributed/work/grid-assignment-native-20261107'
raw=subprocess.check_output(['git','--no-replace-objects','-C',grid,'show',
    '40e9c8dc274a2746018bc1aa08d103cd0187cecc:grid/authority_runtime_v1.py'])
assert hashlib.sha256(raw).hexdigest()=='cfb32db73f1859d9d78b03d886372cc08584c81abd64930b5409a91edc417b64'
module=types.ModuleType('a2_research_lab_review2_measure');sys.modules[module.__name__]=module
exec(compile(raw,'<pinned-primary-layout>','exec'),module.__dict__)
C3=module.canonical
def encode(value): return json.dumps(value,separators=(',',':'),ensure_ascii=True).encode('ascii')
intent=json.loads((OLD/'submit.candidate.canonical.json').read_bytes())
cancel=json.loads((OLD/'cancel.candidate.canonical.json').read_bytes())
submit_digest=hashlib.sha256(C3(intent)).hexdigest()
cancel_digest=hashlib.sha256(C3(cancel)).hexdigest()
plans={}
for name,receipt in baseline['plans'].items():
    raw=(OLD/(name+'.native-plan.json')).read_bytes()
    assert raw.endswith(b'\n') and hashlib.sha256(raw[:-1]).hexdigest()==receipt['encoded_sha256']
    plans[name]=json.loads(raw)
def decode(operation): return json.loads(base64.b64decode(operation['KV']['Value'],validate=True))
grant=next(decode(op) for op in plans['admit'] if 'Value' in op['KV'] and decode(op).get('schema')=='unified.authority.research-lab-assignment.v1-review1')
job=next(decode(op) for op in plans['admit'] if 'Value' in op['KV'] and decode(op).get('schema')=='unified.authority.research-lab-job.v1-review1')
admission_key=next(op['KV']['Key'] for op in plans['admit'] if 'Value' in op['KV'] and decode(op).get('schema')=='unified.authority.research-lab-admission-receipt.v1-review1')
admission_ref=admission_key.rsplit('/',1)[1]
realm=grant['realm_id'];worker=grant['node_id']
L=next(op['KV']['Key'].split('dispatch-receipts/')[0] for op in plans['begin_dispatch'] if 'dispatch-receipts/' in op['KV']['Key'])
dispatch_key=L+'dispatch-receipts/'+job['dispatch_event_id']
schema_by_kind={'ADMISSION':'phase-receipt','DISPATCH':'phase-receipt','COMPUTED_METADATA':'phase-receipt','CANCEL_REQUEST':'phase-receipt'}
schema_map={
    'assignment':'issued-assignment','counter':'assignment-counter',
    'resource-ledger':'resource-ledger','quota-ledger':'quota-ledger',
    'hold':'resource-hold','lease':'lease-lock','command':'original-command','job':'job-state'}
validators={name:Draft202012Validator(json.loads((OUT/(name+'.schema.json')).read_bytes())) for name in set(schema_map.values())|{'phase-receipt'}}
new_plans={};validated=0
kind_by_plan={'admit':'ADMISSION','begin_dispatch':'DISPATCH','record_computed_metadata':'COMPUTED_METADATA','cancel_request':'CANCEL_REQUEST'}
seq_by_plan={'admit':('0','1'),'begin_dispatch':('1','2'),'record_computed_metadata':('2','3'),'cancel_request':('2','3')}
for name,oldops in plans.items():
    operations=copy.deepcopy(oldops);kind=kind_by_plan[name]
    current_ref=admission_ref if name=='admit' else job['dispatch_event_id'] if name=='begin_dispatch' else job['computed_event_id'] if name=='record_computed_metadata' else cancel['request_id']
    previous_seq,next_seq=seq_by_plan[name]
    for operation in operations:
        if 'Value' not in operation['KV']: continue
        value=decode(operation);original_schema=value['schema'];selected=None
        label=original_schema.removeprefix('unified.authority.research-lab-').removesuffix('.v1-review1')
        if label in schema_map:
            selected=schema_map[label]
            value['schema']=original_schema.replace('.v1-review1','.v1-review2')
            if label=='assignment': value['assignment_revision']='5'
            elif label=='counter': value.update(realm_id=realm,worker_id=worker,revision='5',previous_revision='4')
            elif label=='resource-ledger':
                value.update(realm_id=realm,revision='8',previous_revision='7',uncertain_jobs='0',
                    uncertain={k:'0' for k in grant['resources']})
            elif label=='quota-ledger': value.update(realm_id=realm,revision='10',previous_revision='9',uncertain_jobs='0')
            elif label=='hold': value['realm_id']=realm
            elif label=='lease': value.update(realm_id=realm,lease_id=grant['lease_id'])
            elif label=='job':
                value.update(previous_sequence=previous_seq,sequence=next_seq,admission_receipt_id=admission_ref,
                    phase_kind=kind,phase_ref=current_ref)
                value.pop('artifact_retrieval',None)
        else:
            selected='phase-receipt'
            metadata=None
            if kind=='COMPUTED_METADATA':
                metadata={k:value[k] for k in ('artifact_sha256','artifact_bytes','descriptor_sha256','payload_durability','publication')}
            value=dict(schema='unified.authority.research-lab-phase-receipt.v1-review2',kind=kind,event_id=current_ref,
                source_request_id=cancel['request_id'] if kind=='CANCEL_REQUEST' else intent['request_id'],
                source_intent_sha256=cancel_digest if kind=='CANCEL_REQUEST' else submit_digest,
                original_submit_request_id=intent['request_id'],original_submit_intent_sha256=submit_digest,
                job_id=intent['job_id'],assignment_id=grant['assignment_id'],execution_attempt_id=grant['execution_attempt_id'],
                job_sequence=next_seq,artifact_metadata=metadata,committed_at_utc=None,commit_time_status='UNKNOWN_COMMIT_INSTANT')
        # Frozen common-index records are unchanged, not phase receipts.
        if original_schema in ('unified.authority.request-binding.v1','unified.authority.command-key-binding.v1'):
            value=decode(operation);selected=None
        if selected:
            validators[selected].validate(value);validated+=1
        operation['KV']['Value']=base64.b64encode(C3(value)).decode('ascii')
    # Current phase evidence must not be missing/corrupt when advancing RUNNING.
    if name in ('record_computed_metadata','cancel_request'):
        operations.insert(0,{'KV':dict(Verb='check-index',Key=dispatch_key,Index=2**63-1)})
    new_plans[name]=operations
report=dict(scope='EXACT_CANDIDATE_ENVELOPES_NOT_NATIVE_EXECUTION_OR_ISSUER',
    previous_review_measurement_sha256=hashlib.sha256((OLD/'measurement.json').read_bytes()).hexdigest(),
    validated_record_writes=validated,actual_consul_requests=0,plans={},
    sample_predecessors=dict(assignment_counter='4->5',resource_ledger='7->8',quota_ledger='9->10',
        job_sequence='ADMITTED0->1;RUNNING1->2;COMPUTED2->3;cancel-after-running2->3'),
    bounds='Runtime must measure actual complete plan every send; samples are not workload/native qualification')
for name,operations in new_plans.items():
    measurement=module.measure_native_plan(operations)
    report['plans'][name]=dict(operations=measurement.operations,encoded_bytes=measurement.encoded_bytes,
        encoded_sha256=measurement.encoded_sha256,operation_headroom=64-measurement.operations,
        bytes_headroom=32768-measurement.encoded_bytes)
    (OUT/(name+'.native-plan.json')).write_bytes(encode(operations)+b'\n')
(OUT/'measurement.json').write_bytes(json.dumps(report,indent=2).encode()+b'\n')
print(json.dumps(report,indent=2))
