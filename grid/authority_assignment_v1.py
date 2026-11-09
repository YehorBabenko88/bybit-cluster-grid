"""Additive Assignment native Consul substrate; positive domain binding pending.

No native identity issuer, second consensus, public arbitrary-KV endpoint or
execution permission is created. Existing reviewed layout/lease modules unchanged.
"""
import base64,hashlib,json,os,re,stat,uuid
from pathlib import Path
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


# Frozen b513 custody DATA predicates, promoted here as static runtime code.
_RC_MAX_ORIGINAL_BYTES=2048
_RC_MAX_RECEIPT_BYTES=4096
_RC_MAX_DB_BYTES=1048576
_RC_MAX_ROWS=64
_RC_SCHEMA="unified.authority.unqualified-worker-registration-custody.v1-review1"
_RC_FIELDS={"schema","original_registration_request_id","original_registration_intent_sha256","original_registration_intent_base64","event","rpc_kind","rpc_attempt_id","native_session_id","endpoint_sha256","outcome","resources_reserved","effect_permitted"}
_RC_RPCS={"SESSION_CREATE","SESSION_INFO","REGISTRATION_TXN","CONSISTENT_READ","SESSION_DESTROY"}
_RC_MUTATIONS={"SESSION_CREATE","REGISTRATION_TXN","SESSION_DESTROY"}

def _registration_sha(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}",value) is None:raise ValueError("SHA256")

def _parse_registration_intent(raw):
    value=_decode(raw)
    fields={"schema","operation","cluster_id","cluster_generation","realm_id","node_id","worker_inventory_incarnation_id","worker_module_sha256","original_registration_request_id"}
    if set(value)!=fields or value["schema"]!="unified.authority.unqualified-worker-registration-intent.v1-review1" or value["operation"]!="COMMISSION_UNQUALIFIED_WORKER":raise ValueError("CLOSED_REGISTRATION_INTENT")
    for key in ("cluster_id","cluster_generation","realm_id","node_id","worker_inventory_incarnation_id","original_registration_request_id"):_uuid(value[key])
    _registration_sha(value["worker_module_sha256"])
    return value


def _parse_registration_custody(raw,*,original_intent_bytes):
    if type(raw) is not bytes or len(raw)>_RC_MAX_RECEIPT_BYTES:raise ValueError('CUSTODY_RECEIPT_BOUND')
    if type(original_intent_bytes) is not bytes or len(original_intent_bytes)>_RC_MAX_ORIGINAL_BYTES:raise ValueError('CUSTODY_ORIGINAL_BOUND')
    intent=_parse_registration_intent(original_intent_bytes);value=_decode(raw)
    if set(value)!=_RC_FIELDS or value['schema']!=_RC_SCHEMA:raise ValueError('FOREIGN_OR_OPEN_CUSTODY_RECORD')
    if (value['original_registration_request_id']!=intent['original_registration_request_id']
            or value['original_registration_intent_sha256']!=hashlib.sha256(original_intent_bytes).hexdigest()
            or value['original_registration_intent_base64']!=base64.b64encode(original_intent_bytes).decode('ascii')):
        raise ValueError('CUSTODY_ORIGINAL_BINDING')
    if value['resources_reserved'] is not False or value['effect_permitted'] is not False:raise ValueError('NO_CUSTODY_PERMISSION')
    sid=value['native_session_id']
    if sid is not None:
        if type(sid) is not str:raise ValueError('NATIVE_SESSION')
        try:valid=str(uuid.UUID(sid))==sid
        except ValueError:valid=False
        if not valid:raise ValueError('NATIVE_SESSION')
    if value['event']=='ORIGINAL_RETAINED':
        if (value['rpc_kind']!='NONE' or value['outcome']!='NOT_SENT'
                or any(value[field] is not None for field in ('rpc_attempt_id','native_session_id','endpoint_sha256'))):
            raise ValueError('ORIGINAL_PRE_SESSION_ONLY')
    else:
        if value['event'] not in ('RPC_ATTEMPTED','RPC_RESULT') or value['rpc_kind'] not in _RC_RPCS:raise ValueError('CUSTODY_EVENT')
        _uuid(value['rpc_attempt_id']);_registration_sha(value['endpoint_sha256'])
        if value['event']=='RPC_ATTEMPTED' and value['outcome']!='ATTEMPTED':raise ValueError('ATTEMPT_BEFORE_RPC')
        if value['event']=='RPC_RESULT' and value['outcome'] not in ('CONFIRMED','REJECTED','UNKNOWN'):raise ValueError('RPC_OUTCOME')
        if value['rpc_kind']=='SESSION_CREATE':
            confirmed=value['event']=='RPC_RESULT' and value['outcome']=='CONFIRMED'
            if (sid is not None)!=confirmed:raise ValueError('SESSION_CREATION_OWNERSHIP_UNKNOWN')
        elif value['rpc_kind']!='CONSISTENT_READ' and sid is None:raise ValueError('KNOWN_NATIVE_SESSION_REQUIRED')
    return value

def _registration_outer_state(value):
    return 'OBSERVING' if value['event']=='ORIGINAL_RETAINED' or value['outcome']=='CONFIRMED' else 'BLOCKED'

def _replay_registration_custody(records,*,original_intent_bytes):
    """Call only AFTER actual pinned Journal.read verifies its hash chain.

    Public dictionaries/output are local DATA and cannot authorize any RPC.
    """
    from grid.authority_runtime_v1 import canonical
    if type(records) is not list or not 1<=len(records)<=_RC_MAX_ROWS:raise ValueError('CUSTODY_ROW_BOUND')
    attempts={};results={};seen_mutations=set();known_sid=None;transaction='NONE'
    for sequence,row in enumerate(records,1):
        if type(row) is not dict or set(row)!={'sequence','state','receipt','previous_hash'} or type(row['sequence']) is not int or row['sequence']!=sequence:
            raise ValueError('JOURNAL_ROW')
        value=_parse_registration_custody(canonical(row['receipt']),original_intent_bytes=original_intent_bytes)
        if row['state']!=_registration_outer_state(value):raise ValueError('CUSTODY_OUTER_STATE')
        if sequence==1:
            if value['event']!='ORIGINAL_RETAINED':raise ValueError('ORIGINAL_MUST_BE_FIRST')
            continue
        if value['event']=='ORIGINAL_RETAINED':raise ValueError('ONE_ORIGINAL_PER_JOURNAL')
        attempt=value['rpc_attempt_id'];kind=value['rpc_kind'];sid=value['native_session_id']
        if kind!='SESSION_CREATE' and sid is not None and sid!=known_sid:raise ValueError('NO_SESSION_ADOPTION')
        if value['event']=='RPC_ATTEMPTED':
            if attempt in attempts:raise ValueError('RPC_ATTEMPT_REUSE')
            if kind in _RC_MUTATIONS:
                if kind in seen_mutations:raise ValueError('NO_AUTOMATIC_MUTATION_RETRY')
                if kind=='REGISTRATION_TXN' and 'SESSION_DESTROY' in seen_mutations:raise ValueError('NO_REGISTRATION_AFTER_CLEANUP')
                if any(attempts[key]['rpc_kind'] in _RC_MUTATIONS and (key not in results or results[key]['outcome']=='UNKNOWN') for key in attempts):
                    raise ValueError('UNRESOLVED_MUTATION_NO_NEW_MUTATION')
                if kind!='SESSION_CREATE' and (known_sid is None or sid!=known_sid):raise ValueError('NO_SESSION_ADOPTION')
                if kind=='SESSION_DESTROY' and 'REGISTRATION_TXN' in seen_mutations and transaction!='REJECTED':raise ValueError('NO_INVALIDATION_AS_ROLLBACK')
                seen_mutations.add(kind)
            if kind=='REGISTRATION_TXN':transaction='UNKNOWN'
            if kind=='SESSION_CREATE' and known_sid is not None:raise ValueError('NO_NEW_SESSION')
            attempts[attempt]=value
        else:
            prior=attempts.get(attempt)
            if prior is None or attempt in results or prior['rpc_kind']!=kind or prior['endpoint_sha256']!=value['endpoint_sha256']:
                raise ValueError('RPC_RESULT_WITHOUT_EXACT_ATTEMPT')
            if kind!='SESSION_CREATE' and prior['native_session_id']!=sid:raise ValueError('RPC_SESSION_BINDING')
            results[attempt]=value
            if kind=='SESSION_CREATE' and value['outcome']=='CONFIRMED':known_sid=sid
            if kind=='REGISTRATION_TXN':transaction=value['outcome']
    return dict(local_transaction_report=transaction,native_session_id=known_sid,
        unresolved_rpc_attempts=[key for key in attempts if key not in results or results[key]['outcome']=='UNKNOWN'],
        resources_reserved=False,effect_permitted=False)

class RegistrationCustodyUnavailable(RuntimeError):pass

def _registration_ordinary(path,*,file=False):
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
        raise RegistrationCustodyUnavailable('ORDINARY_LOCAL_ROOT_PATH_REQUIRED')
    if file and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):
        raise RegistrationCustodyUnavailable('ORDINARY_SINGLE_LINK_FILE_REQUIRED')
    return info

def _registration_local_volume(path):
    if os.name=='nt':
        import ctypes
        if not path.drive or path.drive.startswith('\\\\') or ctypes.windll.kernel32.GetDriveTypeW(path.drive+'\\')!=3:
            raise RegistrationCustodyUnavailable('FIXED_LOCAL_ROOT_VOLUME_REQUIRED')
    elif os.name=='posix':
        # Fail closed on unknown/network filesystem types; no mount mutation.
        mounts=Path('/proc/self/mountinfo').read_text().splitlines();matches=[]
        device=path.stat().st_dev;device_id=str(os.major(device))+':'+str(os.minor(device))
        for line in mounts:
            left,right=line.split(' - ',1);parts=left.split();mount=parts[4]
            mount=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),mount)
            if parts[2]==device_id and (path==Path(mount) or Path(mount) in path.parents):matches.append((len(mount),right.split()[0]))
        if not matches or max(matches)[1] not in ('ext4','ext3','ext2','xfs','btrfs','overlay','tmpfs'):
            raise RegistrationCustodyUnavailable('QUALIFIED_LOCAL_FILESYSTEM_REQUIRED')
    else:raise RegistrationCustodyUnavailable('OS_LOCK_BACKEND_UNSUPPORTED')

class RootRegistrationCustody:
    """Actual LOCAL single-writer Journal owner, never Root role/native proof.

    Server-selected path/private ACL and Root-only lifecycle remain deployment
    prerequisites. The kernel lock excludes cooperating owner processes; it
    does not protect against a privileged process bypassing this adapter.
    No native RPC, session, registration write or positive grant is implemented.
    """
    def __init__(self,actual_journal,*,original_intent_bytes):
        from unified_system.journal import Journal
        import unified_system.journal as journal_module
        if type(actual_journal) is not Journal:raise TypeError('FIXED_ACTUAL_ROOT_JOURNAL_REQUIRED')
        source=Path(journal_module.__file__).absolute()
        if hashlib.sha256(source.read_bytes()).hexdigest()!='9f170cf33f8cdd79baef6fa633d03bebf9eb4b594c54c9cf8dd6c7cb9810bbc3':
            raise RegistrationCustodyUnavailable('FIXED_ROOT_JOURNAL_SOURCE_REQUIRED')
        if type(original_intent_bytes) is not bytes or len(original_intent_bytes)>_RC_MAX_ORIGINAL_BYTES:raise ValueError('ORIGINAL_BOUND')
        self._intent=_parse_registration_intent(original_intent_bytes);self._original=original_intent_bytes
        self._journal=actual_journal;self._path=actual_journal.path
        self._lock_fd=None;self._db_fd=None;self._closed=False;self._owner_pid=os.getpid();self._allocated_new=False
        try:
            if not self._path.is_absolute() or self._path!=self._path.resolve():raise RegistrationCustodyUnavailable('CANONICAL_ROOT_ALLOCATED_PATH_REQUIRED')
            for parent in self._path.parents:_registration_ordinary(parent)
            _registration_local_volume(self._path.parent)
            self._lock_path=self._path.with_name(self._path.name+'.registration-owner.lock')
            flags=os.O_RDWR|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
            try:
                self._lock_fd=os.open(self._lock_path,flags|os.O_CREAT|os.O_EXCL,0o600);new_lock=True
            except FileExistsError:
                _registration_ordinary(self._lock_path,file=True)
                self._lock_fd=os.open(self._lock_path,flags);new_lock=False
            os.set_inheritable(self._lock_fd,False)
            lock_info=_registration_ordinary(self._lock_path,file=True)
            if (lock_info.st_dev,lock_info.st_ino)!=(os.fstat(self._lock_fd).st_dev,os.fstat(self._lock_fd).st_ino):
                raise RegistrationCustodyUnavailable('LOCK_IDENTITY_CHANGED')
            try:
                if os.name=='nt':
                    import msvcrt
                    os.lseek(self._lock_fd,0,os.SEEK_SET);msvcrt.locking(self._lock_fd,msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self._lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RegistrationCustodyUnavailable('EXCLUSIVE_ROOT_JOURNAL_OWNERSHIP_UNAVAILABLE') from None
            if new_lock:
                try:self._db_fd=os.open(self._path,flags|os.O_CREAT|os.O_EXCL,0o600)
                except FileExistsError:raise RegistrationCustodyUnavailable('FOREIGN_EXISTING_DATABASE_NOT_ADOPTED') from None
                self._allocated_new=True
            else:
                _registration_ordinary(self._path,file=True);self._db_fd=os.open(self._path,flags)
            os.set_inheritable(self._db_fd,False)
            db_info=_registration_ordinary(self._path,file=True)
            self._db_identity=(db_info.st_dev,db_info.st_ino)
            header=canonical(dict(schema='unified.local.registration-journal-owner.v1',
                db_path_sha256=hashlib.sha256(os.fsencode(os.path.normcase(str(self._path)))).hexdigest(),
                original_registration_intent_sha256=hashlib.sha256(self._original).hexdigest(),
                device=str(db_info.st_dev),inode=str(db_info.st_ino)))
            if new_lock:
                os.lseek(self._lock_fd,0,os.SEEK_SET)
                if os.write(self._lock_fd,header)!=len(header):raise RegistrationCustodyUnavailable('LOCK_HEADER_RETENTION_UNKNOWN')
                os.fsync(self._lock_fd)
                # Only the file exclusively created by THIS constructor may be
                # initialized. Existing foreign/empty/corrupt files are not.
                Journal.initialize(self._journal)
            else:
                if not 0<os.fstat(self._lock_fd).st_size<=1024:raise RegistrationCustodyUnavailable('FOREIGN_LOCK_HEADER')
                os.lseek(self._lock_fd,0,os.SEEK_SET)
                if os.read(self._lock_fd,1025)!=header:raise RegistrationCustodyUnavailable('FOREIGN_LOCK_HEADER')
            self._header=header
            self._read_verified(allow_empty=self._allocated_new)
        except BaseException as exc:
            try:self.close()
            except BaseException as cleanup:exc.add_note('Custody constructor cleanup: '+type(cleanup).__name__)
            raise

    def _ensure_owned(self):
        if self._closed or self._owner_pid!=os.getpid() or self._lock_fd is None or self._db_fd is None:
            raise RegistrationCustodyUnavailable('LOCAL_CUSTODY_CLOSED_OR_FOREIGN_PROCESS')
        if self._journal.path!=self._path or self._path!=self._path.resolve():raise RegistrationCustodyUnavailable('JOURNAL_PATH_CHANGED')
        for parent in self._path.parents:_registration_ordinary(parent)
        info=_registration_ordinary(self._path,file=True);held=os.fstat(self._db_fd)
        if (info.st_dev,info.st_ino)!=self._db_identity or (held.st_dev,held.st_ino)!=self._db_identity or held.st_nlink!=1:
            raise RegistrationCustodyUnavailable('JOURNAL_FILE_IDENTITY_CHANGED')
        if not 0<info.st_size<=_RC_MAX_DB_BYTES:raise RegistrationCustodyUnavailable('JOURNAL_FILE_BOUND')
        lock=_registration_ordinary(self._lock_path,file=True);held_lock=os.fstat(self._lock_fd)
        if (lock.st_dev,lock.st_ino)!=(held_lock.st_dev,held_lock.st_ino) or held_lock.st_nlink!=1 or not 0<lock.st_size<=1024:
            raise RegistrationCustodyUnavailable('LOCK_FILE_IDENTITY_CHANGED')
        os.lseek(self._lock_fd,0,os.SEEK_SET)
        if os.read(self._lock_fd,1025)!=self._header:raise RegistrationCustodyUnavailable('LOCK_HEADER_CHANGED')
        for suffix in ('-wal','-shm','-journal'):
            try:self._path.with_name(self._path.name+suffix).lstat()
            except FileNotFoundError:continue
            raise RegistrationCustodyUnavailable('SIDECAR_REQUIRES_EXPLICIT_OWNER_RECOVERY')

    def _read_verified(self,*,allow_empty=False):
        from unified_system.journal import Journal
        self._ensure_owned()
        try:rows=Journal.read(self._journal)
        except Exception as exc:raise RegistrationCustodyUnavailable('CORRUPT_OR_FOREIGN_JOURNAL') from exc
        if not rows and allow_empty:return rows
        _replay_registration_custody(rows,original_intent_bytes=self._original)
        self._ensure_owned();return rows

    def _append(self,value):
        from unified_system.journal import Journal
        _parse_registration_custody(canonical(value),original_intent_bytes=self._original)
        rows=self._read_verified(allow_empty=self._allocated_new)
        if len(rows)>=_RC_MAX_ROWS:raise RegistrationCustodyUnavailable('CUSTODY_ROW_BOUND')
        proposed=rows+[dict(sequence=len(rows)+1,state=_registration_outer_state(value),receipt=value,previous_hash='0'*64)]
        _replay_registration_custody(proposed,original_intent_bytes=self._original)
        Journal.append(self._journal,_registration_outer_state(value),value,expected_sequence=len(rows))
        self._allocated_new=False;self._read_verified()

    def retain_original(self):
        self._append(dict(schema=_RC_SCHEMA,original_registration_request_id=self._intent['original_registration_request_id'],
            original_registration_intent_sha256=hashlib.sha256(self._original).hexdigest(),
            original_registration_intent_base64=base64.b64encode(self._original).decode('ascii'),event='ORIGINAL_RETAINED',
            rpc_kind='NONE',rpc_attempt_id=None,native_session_id=None,endpoint_sha256=None,outcome='NOT_SENT',resources_reserved=False,effect_permitted=False))

    def begin_rpc(self,*,rpc_kind,rpc_attempt_id,endpoint_sha256):
        rows=self._read_verified();state=_replay_registration_custody(rows,original_intent_bytes=self._original)
        value=dict(rows[0]['receipt'],event='RPC_ATTEMPTED',rpc_kind=rpc_kind,rpc_attempt_id=rpc_attempt_id,
            native_session_id=None if rpc_kind=='SESSION_CREATE' else state['native_session_id'],endpoint_sha256=endpoint_sha256,outcome='ATTEMPTED')
        self._append(value)

    def finish_rpc(self,*,rpc_attempt_id,outcome,native_session_id=None):
        rows=self._read_verified()
        prior=next((row['receipt'] for row in rows if row['receipt']['event']=='RPC_ATTEMPTED' and row['receipt']['rpc_attempt_id']==rpc_attempt_id),None)
        if prior is None:raise ValueError('KNOWN_RPC_ATTEMPT_REQUIRED')
        if prior['rpc_kind']!='SESSION_CREATE' and native_session_id is not None and native_session_id!=prior['native_session_id']:
            raise ValueError('RPC_RESULT_SESSION_MISMATCH')
        self._append(dict(prior,event='RPC_RESULT',outcome=outcome,
            native_session_id=native_session_id if prior['rpc_kind']=='SESSION_CREATE' else prior['native_session_id']))

    def read_state(self):
        return _replay_registration_custody(self._read_verified(),original_intent_bytes=self._original)

    def close(self):
        if self._closed:return
        self._closed=True;errors=[]
        for name in ('_db_fd','_lock_fd'):
            fd=getattr(self,name,None);setattr(self,name,None)
            if fd is not None:
                try:os.close(fd)  # Kernel releases owned lock; persistent file is NEVER deleted.
                except OSError as exc:errors.append(exc)
        if errors:raise RegistrationCustodyUnavailable('LOCAL_CUSTODY_CLOSE_UNKNOWN') from errors[0]

    def __enter__(self):
        try:self._ensure_owned()
        except BaseException as error:
            try:self.close()
            except BaseException as cleanup:error.add_note('Custody entry cleanup: '+type(cleanup).__name__)
            raise
        return self
    def __copy__(self):raise TypeError('LOCAL_CUSTODY_NOT_COPYABLE')
    def __deepcopy__(self,memo):raise TypeError('LOCAL_CUSTODY_NOT_COPYABLE')
    def __reduce__(self):raise TypeError('LOCAL_CUSTODY_NOT_SERIALIZABLE')
    def __exit__(self,kind,error,traceback):
        try:self.close()
        except BaseException as cleanup:
            if error is None:raise
            error.add_note('Custody close failure: '+type(cleanup).__name__)
        return False
