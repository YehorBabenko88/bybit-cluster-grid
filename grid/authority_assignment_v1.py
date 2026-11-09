"""Additive Assignment native Consul substrate; positive domain binding pending.

No native identity issuer, second consensus, public arbitrary-KV endpoint or
execution permission is created. Existing reviewed layout/lease modules unchanged.
"""
import base64,hashlib,json,re,uuid
import httpx
from dataclasses import dataclass
from urllib.parse import quote
from .authority_runtime_v1 import RuntimeLayout,canonical,measure_native_plan
from .coordination import ConsulSessionAuthority,CoordinationLost,CoordinationUnavailable

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
    async def _read_snapshot(self,keys):
        """Private one-Txn consistent facts, NOT identity/admission/closure proof.

        Public owners must derive their exact key set and check current rights.
        Missing at this snapshot is not proof an original never committed.
        """
        namespace=getattr(getattr(self.authority,'config',None),'namespace','')+'/'
        if (type(keys) is not tuple or not 1<=len(keys)<=64
                or any(type(k) is not str or not 1<=len(k)<=1024 or not k.startswith(namespace)
                       or re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.:-]+)*',k) is None
                       or any(part in ('.','..') for part in k.split('/')) for k in keys)
                or len(set(keys))!=len(keys)):
            raise ValueError('SNAPSHOT_KEY_INVENTORY')
        if (type(self.authority) is not ConsulSessionAuthority or not self.authority._owns_client
                or type(self.authority.client) is not httpx.AsyncClient
                or type(self.authority.client._transport) is not httpx.AsyncHTTPTransport):
            raise AssignmentUnavailable('ACTUAL_CONSUL_SNAPSHOT_SOURCE_REQUIRED')
        result=await self._transaction([{'KV':dict(Verb='get-or-empty',Key=k)} for k in keys],read_only=True)
        if result.get('KnownLeader') is not True or result.get('ResultsFilteredByACLs') is not False:
            raise AssignmentUnavailable('CONSISTENT_UNFILTERED_SNAPSHOT_UNAVAILABLE')
        records=[]
        try:
            for key,item in zip(keys,result['Results'],strict=True):
                if set(item)!={'KV'} or type(item['KV']) is not dict:raise ValueError('SNAPSHOT_ROW')
                row=item['KV'];index=row['ModifyIndex'];created=row['CreateIndex']
                if (row.get('Key')!=key or type(index) is not int or not 0<=index<2**63
                        or type(created) is not int or not 0<=created<=index):raise ValueError('SNAPSHOT_INDEX')
                session=row.get('Session','')
                if type(session) is not str:raise ValueError('SNAPSHOT_SESSION')
                if session and str(uuid.UUID(session))!=session:raise ValueError('SNAPSHOT_SESSION')
                if index==0:
                    if created!=0 or row.get('Value') is not None or session:raise ValueError('SNAPSHOT_ABSENCE')
                    raw=None
                else:
                    if created==0 or type(row.get('Value')) is not str:raise ValueError('SNAPSHOT_VALUE')
                    raw=base64.b64decode(row['Value'],validate=True);_decode(raw)
                records.append(CapturedRecord(key,index,raw,session))
        except (ValueError,TypeError,KeyError,UnicodeError) as exc:
            raise AssignmentUnavailable('NATIVE_SNAPSHOT_ENCODING') from exc
        return tuple(records)
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

@dataclass(frozen=True)
class ResearchAdmissionResult:
    """NEGATIVE_PATH observation DATA, never a receipt or execution capability."""
    outcome: str
    reason: str
    original_intent_sha256: str
    commit_status: str='NOT_ATTEMPTED'
    effect_permitted: bool=False

class ResearchLabAuthority:
    """Internal authenticated negative path over the existing Grid authority.

    No job writes, queue, second broker, resource proof or positive permission.
    Existing committed jobs are deliberately UNKNOWN until a qualified resolver
    checks their full original/receipt/assignment/phase dependencies.
    """
    def __init__(self,authority,generation,*,broker):
        from unified_system.gateway_research_identity import ResearchIdentityBroker
        if (type(authority) is not ConsulSessionAuthority or type(broker) is not ResearchIdentityBroker
                or broker._authority is not authority or broker._generation!=generation):
            raise TypeError('ACTUAL_SAME_AUTHORITY_RESEARCH_BROKER_REQUIRED')
        self._native=AssignmentAuthority(authority,generation)
        self._broker=broker

    async def _observe(self,original,*,context,scope,leader=None):
        from unified_system.gateway_research_identity import ResearchIdentityBroker
        command=_decode(original)
        fields={'schema','operation','cluster_id','cluster_generation','request_id','job_id',
                'original_actor_principal_id','quota_owner_id','idempotency_key',
                'commissioned_profile_sha256','input_request_sha256','producer_head','resources'}
        if (set(command)!=fields or command['schema']!='unified.gateway.lab-job-submit.v1-review1'
                or command['operation']!='SUBMIT_RESEARCH'):
            raise ValueError('EXACT_ORIGINAL_LAB13_REQUIRED')
        authority=self._native.authority
        if scope=='SUBMIT_RESEARCH' and not await authority.validate(leader):
            raise AssignmentUnavailable('CURRENT_GRID_LEADER_REQUIRED')
        capture=await ResearchIdentityBroker.capture_current(self._broker,context,scope=scope,request_bytes=original)
        identity=ResearchIdentityBroker.require_capture(self._broker,capture,expected_authority=authority,scope=scope,request_bytes=original)
        profile=_decode(identity.records[1].raw)
        if (profile.get('schema')!='unified.authority.target-bound-research-profile.v2-review1'
                or profile.get('cluster_id')!=command['cluster_id']
                or command['cluster_generation']!=self._native.generation
                or identity.actor_id!=command['original_actor_principal_id']
                or identity.quota_owner_id!=command['quota_owner_id']
                or identity.profile_sha256!=command['commissioned_profile_sha256']):
            raise AssignmentUnavailable('CURRENT_TARGET_BOUND_PROFILE_REQUIRED')
        realm=_uuid(profile['realm_id']);job=_uuid(command['job_id'])
        namespace=authority.config.namespace
        if namespace!='unified/'+_uuid(command['cluster_id']):raise ValueError('CLUSTER_BINDING')
        job_key=namespace+'/runtime-v1/research-lab-v1/'+realm+'/jobs/'+job
        keys=tuple(r.key for r in identity.records)
        generation_key=namespace+'/commands/generation'
        if generation_key not in keys:raise AssignmentUnavailable('CURRENT_GENERATION_SOURCE_REQUIRED')
        rows=await self._native._read_snapshot(keys+(authority.key,job_key))
        for current,prior in zip(rows,identity.records):
            if (current.key,current.index,current.raw,current.session)!=(prior.key,prior.index,prior.raw,prior.session):
                raise AssignmentUnavailable('CURRENT_IDENTITY_SNAPSHOT_CHANGED')
        if _decode(rows[keys.index(generation_key)].raw)!={'generation':self._native.generation}:
            raise AssignmentUnavailable('GENERATION_NOT_CURRENT')
        if scope=='SUBMIT_RESEARCH':
            lock=rows[-2]
            if lock.index!=leader.token or lock.session!=leader.session_id or not await authority.validate(leader):
                raise AssignmentUnavailable('CURRENT_GRID_LEADER_REQUIRED')
        # Recheck the actual fixed issuer, exact original and local peer/expiry
        # after all awaits; this does not establish Raft commit-time UTC.
        ResearchIdentityBroker.require_capture(self._broker,capture,expected_authority=authority,scope=scope,request_bytes=original)
        return rows[-1]

    async def submit(self,original_lab13_bytes,*,context,leader,owned_attempt=None):
        job=await self._observe(original_lab13_bytes,context=context,scope='SUBMIT_RESEARCH',leader=leader)
        # No caller-supplied attempt/boolean/method shape can bypass this gate.
        reason='JOB_RECONCILIATION_API_UNQUALIFIED' if job.index else 'NATIVE_WORKER_RESOURCE_API_UNQUALIFIED'
        return ResearchAdmissionResult('UNKNOWN' if job.index else 'DENIED',reason,hashlib.sha256(original_lab13_bytes).hexdigest())

    async def lookup(self,original_lab13_bytes,*,context):
        await self._observe(original_lab13_bytes,context=context,scope='READ_RESEARCH')
        # Snapshot absence is not never-committed evidence. Do not manufacture a
        # NOT_FOUND receipt or expose arbitrary native job record payloads.
        return ResearchAdmissionResult('UNKNOWN','JOB_RECONCILIATION_API_UNQUALIFIED',hashlib.sha256(original_lab13_bytes).hexdigest())
