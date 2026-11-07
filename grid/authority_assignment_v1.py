"""Additive Assignment native Consul substrate; positive domain binding pending.

No native identity issuer, second consensus, public arbitrary-KV endpoint or
execution permission is created. Existing reviewed layout/lease modules unchanged.
"""
import base64,json,re,uuid
from dataclasses import dataclass
from urllib.parse import quote
from .authority_runtime_v1 import RuntimeLayout,canonical,measure_native_plan
from .coordination import CoordinationLost,CoordinationUnavailable

class AssignmentUnavailable(RuntimeError):pass

def _uuid(value):
    if type(value) is not str:raise ValueError('UUID')
    try:valid=str(uuid.UUID(value,version=4))==value
    except ValueError:valid=False
    if not valid:raise ValueError('UUID')
    return value

def _positive(value):
    if type(value) is not str or not re.fullmatch(r'[1-9][0-9]{0,18}',value) or int(value)>2**63-1:raise ValueError('POSITIVE_U63')
    return value

@dataclass(frozen=True)
class AssignmentLayout(RuntimeLayout):
    """NEW additive key families. Values, schemas and native admission separate."""
    def storage_binding(self,node_id,volume_id,instance_id,reservation_id,policy_id,basis_id,*,policy_revision,basis_revision):
        node,volume,instance,reservation,policy,basis=map(_uuid,(node_id,volume_id,instance_id,reservation_id,policy_id,basis_id))
        base=self.prefix+'storage/'+node+'/'+volume+'/'+instance+'/'
        return dict(issuance=self.prefix+'storage-reservations/'+reservation+'/issuance',
            lifecycle=self.prefix+'storage-reservations/'+reservation+'/lifecycle',
            policy=base+'policies/'+policy+'/'+_positive(policy_revision),accounting=base+'accounting',
            budget_basis=self.prefix+'storage-budget-bases/'+basis+'/'+_positive(basis_revision))
    def storage_policy_current(self,node_id,volume_id,instance_id):
        return self.prefix+'storage/'+'/'.join(map(_uuid,(node_id,volume_id,instance_id)))+'/policy-current'
    def runtime_policy(self,policy_id):return self.prefix+'security/policies/'+_uuid(policy_id)

@dataclass(frozen=True)
class CapturedRecord:
    key: str
    index: int
    raw: bytes|None
    session: str=''


def _check(record):
    return {'KV':dict(Verb='check-index',Key=record.key,Index=record.index)} if record.index else {'KV':dict(Verb='check-not-exists',Key=record.key)}

def _cas(key,index,value):
    raw=canonical(value)
    return {'KV':dict(Verb='cas',Key=key,Index=index,Value=base64.b64encode(raw).decode('ascii'))}


def _decode(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('DUPLICATE_KEY')
            value[key]=item
        return value
    def number(_):raise ValueError('NUMBER_NOT_ALLOWED')
    if type(raw) is not bytes or not 0<len(raw)<=16384:raise ValueError('RECORD_CAP')
    depth=0;quoted=False;escaped=False
    for char in raw:
        if quoted:
            if escaped:escaped=False
            elif char==92:escaped=True
            elif char==34:quoted=False
        elif char==34:quoted=True
        elif char in (91,123):
            depth+=1
            if depth>12:raise ValueError('RECORD_DEPTH')
        elif char in (93,125):
            depth-=1
            if depth<0:raise ValueError('RECORD_JSON')
    value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,parse_int=number,parse_float=number,parse_constant=number)
    if type(value) is not dict or canonical(value)!=raw:raise ValueError('RECORD_CANONICAL')
    return value

RUNTIME_OPERATIONS=frozenset(('ASSIGN','DISPATCH','PUBLISH','READ_ASSIGNMENT','READ_PUBLICATION','RENEW_BEGIN','RENEW_FINALIZE','REVOKE','VERIFY_ASSIGNMENT'))

def parse_runtime_policy(raw):
    """Validate NEW untrusted policy data; never native admission/issuance."""
    value=_decode(raw)
    fields={'schema','namespace','policy_id','cluster_id','principal_id','actor_session_id','enrollment_id','actor_node_id','identity_policy_id','revision','state','partition','job_ids','operations'}
    if set(value)!=fields or value['schema']!='unified.authority.runtime-actor-policy.v1-review2':raise ValueError('POLICY_PROFILE')
    for field in ('policy_id','cluster_id','principal_id','actor_session_id','enrollment_id','actor_node_id','identity_policy_id'):_uuid(value[field])
    _positive(value['revision'])
    if value['namespace']!='unified/'+value['cluster_id'] or value['state'] not in ('ACTIVE','REVOKED'):raise ValueError('POLICY_BINDING')
    part=value['partition']
    if type(part) is not dict or set(part)!={'dataset_id','source_id','partition_id'}:raise ValueError('POLICY_PARTITION')
    _uuid(part['dataset_id'])
    def identifier(item):
        if type(item) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',item) is None:raise ValueError('POLICY_ID')
    for field in ('source_id','partition_id'):identifier(part[field])
    jobs=value['job_ids'];operations=value['operations']
    if type(jobs) is not list or not 1<=len(jobs)<=32:raise ValueError('POLICY_JOB_SET')
    for item in jobs:identifier(item)
    if jobs!=sorted(set(jobs)):raise ValueError('POLICY_JOB_ORDER')
    if type(operations) is not list or not 1<=len(operations)<=len(RUNTIME_OPERATIONS):raise ValueError('POLICY_OPERATIONS')
    if any(type(item) is not str or item not in RUNTIME_OPERATIONS for item in operations) or operations!=sorted(set(operations)):raise ValueError('POLICY_OPERATION_ORDER')
    return value

class AssignmentAuthority:
    """Existing authority instance only; all native effect operations async.

    Private native primitives below establish actual Consul binding. Their tests
    are not a real issued Assignment/native identity acceptance. Public positive
    domain operations require exact co-approved schemas and actual Root provider.
    """
    def __init__(self,authority,generation,*,native_provider=None):
        self.authority=authority;self.generation=_uuid(generation);self.native_provider=native_provider
        if native_provider is not None:
            if type(native_provider) in (bool,dict) or not callable(getattr(native_provider,'require_current',None)) or not callable(getattr(native_provider,'verify_records',None)):
                raise TypeError('ACTUAL_NATIVE_PROVIDER_REQUIRED')
        self.prefix=getattr(getattr(authority,'config',None),'namespace','')+'/runtime-v1/'
    async def _read(self,key):
        rows=await self.authority._request('GET','/v1/kv/'+quote(key,safe='/'),params={'consistent':''},missing_ok=True)
        if rows is None:return CapturedRecord(key,0,None)
        if type(rows) is not list or len(rows)!=1:raise AssignmentUnavailable('NATIVE_RECORD_INVENTORY')
        row=rows[0]
        if type(row) is not dict or row.get('Key')!=key or type(row.get('ModifyIndex')) is not int or not 0<row['ModifyIndex']<2**63:raise AssignmentUnavailable('NATIVE_RECORD_INDEX')
        try:
            raw=base64.b64decode(row['Value'],validate=True);_decode(raw)
            session=row.get('Session','')
            if type(session) is not str:raise ValueError('SESSION_TYPE')
        except (ValueError,TypeError,KeyError,UnicodeError) as exc:raise AssignmentUnavailable('NATIVE_RECORD_ENCODING') from exc
        return CapturedRecord(key,row['ModifyIndex'],raw,session)
    async def _leader_fence(self,leader):
        if not await self.authority.validate(leader):raise AssignmentUnavailable('CURRENT_GRID_LEADER_REQUIRED')
        key=self.authority.config.namespace+'/commands/generation';generation=await self._read(key)
        if not generation.index or _decode(generation.raw)!={'generation':self.generation}:raise AssignmentUnavailable('GENERATION_NOT_CURRENT')
        return [_check(generation),{'KV':dict(Verb='check-session',Key=self.authority.key,Session=leader.session_id)},
                {'KV':dict(Verb='check-index',Key=self.authority.key,Index=leader.token)}]
    async def _transaction(self,operations,*,read_only=False):
        measure_native_plan(operations) # actual64op/32768encoded limit, not proof.
        result=await self.authority._request('PUT','/v1/txn',json=operations,**({'params':{'consistent':''}} if read_only else {}))
        if (type(result) is not dict or result.get('Errors') or type(result.get('Results')) is not list
                or len(result['Results'])!=len(operations) or any(type(item) is not dict for item in result['Results'])):
            raise AssignmentUnavailable('NATIVE_TRANSACTION_OUTCOME_UNKNOWN')
        return result
    async def execute(self,original_request_bytes,*,context,leader):
        if self.native_provider is None:raise AssignmentUnavailable('ACTUAL_NATIVE_PROVIDER_UNAVAILABLE')
        # Native/provider and exact positive domain profile/ABI are not yet
        # qualified. Do not manufacture a grant from data or method presence.
        raise AssignmentUnavailable('ASSIGNMENT_DOMAIN_PROFILE_NOT_APPROVED')
    async def reconcile(self,original_request_bytes,*,context):
        raise AssignmentUnavailable('ASSIGNMENT_RECEIPT_PROFILE_NOT_APPROVED')
