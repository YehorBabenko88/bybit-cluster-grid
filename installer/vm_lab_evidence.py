"""Offline future-observer draft contract. Hash integrity never authenticates facts."""
import hashlib
from installer.vm_lab_json import canonical, load
from installer.vm_lab_plan import validate_vm_lab_plan, _shape, _need, _guid, _digest


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def draft(plan, observer_id):
    report=validate_vm_lab_plan(plan);_guid(observer_id)
    payload={
        'lab_id':plan['lab_id'], 'vm_id':plan['vm_id'], 'host_id':plan['host']['id'],
        'observer':{'id':observer_id,'authority':'UNAUTHENTICATED_DECLARATION'},
        'image_sha256':plan['image']['sha256'], 'quotas':dict(plan['quotas']),
        'identity_evidence':'NOT_COLLECTED', 'isolation_evidence':'NOT_COLLECTED',
        'approval_evidence':'NOT_AUTHENTICATED',
        'negative_cases':[dict(case=c['case'],execution='NOT_RUN',assurance='BLOCKED_UNPROVEN')
                          for c in report['negative_cases']],
    }
    return {'schema':1,'kind':'VmLabIsolationEvidenceDraft','plan_sha256':digest(plan),
            'payload':payload,'payload_sha256':digest(payload)}


def inspect_evidence(raw, plan):
    validate_vm_lab_plan(plan)
    envelope=load(raw)
    _shape(envelope,'schema kind plan_sha256 payload payload_sha256')
    _need(type(envelope['schema']) is int and envelope['schema']==1 and
          envelope['kind']=='VmLabIsolationEvidenceDraft','VM_EVIDENCE_SCHEMA_INVALID')
    _digest(envelope['plan_sha256']);_digest(envelope['payload_sha256'])
    _need(envelope['plan_sha256']==digest(plan),'VM_EVIDENCE_PLAN_MISMATCH')
    payload=envelope['payload']
    _shape(payload,'lab_id vm_id host_id observer image_sha256 quotas identity_evidence isolation_evidence approval_evidence negative_cases')
    observer=payload['observer'];_shape(observer,'id authority');_guid(observer['id'])
    # Compare the entire strict draft against this plan, including the exact case
    # catalogue, types, identities and immutable NOT_RUN states. Rehashing forged
    # PASS/token/approval metadata cannot change this contract.
    expected=draft(plan,observer['id'])
    _need(envelope['payload_sha256']==digest(payload),'VM_EVIDENCE_PAYLOAD_MISMATCH')
    _need(canonical(payload)==canonical(expected['payload']),'VM_EVIDENCE_DRAFT_INVALID')
    return {'schema':1,'status':'BLOCKED','mode':'PlanOnly','integrity':'MATCH_METADATA_ONLY',
            'authentication':'UNVERIFIED','execution_authorized':False,'physical_ready':False,
            'readiness_passed':False,'verified_safety_cases':0,
            'negative_cases':[dict(c) for c in expected['payload']['negative_cases']],
            'blockers':['OBSERVER_NOT_AUTHENTICATED','DECLARATIONS_NOT_ATTESTED',
                        'ALL_GUEST_NEGATIVE_CASES_NOT_RUN','ACL_NAMESPACE_ABA','GLOBAL_KERNEL_EXHAUSTION']}
