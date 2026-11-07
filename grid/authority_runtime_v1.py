"""Proposed fixed runtime key registry and native plan bounds.
No producer/admission/election/HTTP API is enabled by this module. Issued domain
schemas and common index need fresh Root/A3/A4/A5 agreement before wiring.
"""
from dataclasses import dataclass
import hashlib,json,re,uuid

_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
_SHA=re.compile(r'[0-9a-f]{64}')

def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):raise ValueError('IDENTIFIER')
    return value

def _uuid(value):
    if type(value) is not str or str(uuid.UUID(value,version=4))!=value:raise ValueError('UUID')
    return value

def canonical(value):
    def walk(v,depth=0):
        if depth>12:raise ValueError('DEPTH')
        if v is None or type(v) is bool:return
        if type(v) is str:
            if len(v)>16384 or any(not 32<=ord(c)<=126 for c in v):raise ValueError('ASCII_STRING')
            return
        if type(v) is list:
            if len(v)>32:raise ValueError('ARRAY_CAP')
            for x in v:walk(x,depth+1)
            return
        if type(v) is dict:
            if len(v)>64:raise ValueError('MEMBER_CAP')
            for k,x in v.items():_id(k);walk(x,depth+1)
            return
        raise ValueError('NON_JSON_OR_NUMBER')
    walk(value)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    if len(raw)>16384:raise ValueError('RECORD_CAP')
    return raw

def common_key_preimage(cluster_id,quota_owner_id,actor_principal_id,idempotency_key):
    return dict(schema='unified.authority.command-key.v1',cluster_id=_uuid(cluster_id),quota_owner_id=_id(quota_owner_id),
        original_actor_principal_id=_id(actor_principal_id),idempotency_key=_id(idempotency_key))

@dataclass(frozen=True)
class PartitionIdentity:
    cluster_id: str
    dataset_id: str
    source_id: str
    partition_id: str
    def __post_init__(self):
        _uuid(self.cluster_id);_uuid(self.dataset_id);_id(self.source_id);_id(self.partition_id)
    @property
    def digest(self):
        return hashlib.sha256(canonical(dict(schema='unified.authority.partition-identity.v1',**self.__dict__))).hexdigest()

@dataclass(frozen=True)
class RuntimeLayout:
    identity: PartitionIdentity
    def __post_init__(self):
        if type(self.identity) is not PartitionIdentity:raise ValueError('PARTITION_IDENTITY')
    @property
    def namespace(self):return 'unified/'+self.identity.cluster_id
    @property
    def prefix(self):return self.namespace+'/runtime-v1/'
    @property
    def partition(self):return self.prefix+'partitions/'+self.identity.digest+'/'
    @property
    def assignment(self):return self.partition+'assignment'
    @property
    def counters(self):return self.partition+'assignment-counters'
    @property
    def checkpoint(self):return self.partition+'checkpoint'
    @property
    def coverage(self):return self.partition+'coverage'
    @property
    def source_policy(self):return self.partition+'source-policy'
    @property
    def dataset_head(self):return self.prefix+'datasets/'+self.identity.dataset_id+'/head'
    def node(self,node_id,family):
        if family not in ('registration','policy','observation-current','freshness','resource-ledger'):raise ValueError('NODE_FAMILY')
        return self.prefix+'nodes/'+_uuid(node_id)+'/'+family
    def resource_reservation(self,reservation_id):return self.prefix+'reservations/'+_uuid(reservation_id)
    def observation(self,observation_id):return self.prefix+'observations/'+_uuid(observation_id)
    def execution_attempt(self,node_id,attempt_id):return self.prefix+'nodes/'+_uuid(node_id)+'/attempts/'+_uuid(attempt_id)
    def lease(self,lease_id,family):
        if family not in ('lock','binding'):raise ValueError('LEASE_FAMILY')
        return self.prefix+'leases/'+_uuid(lease_id)+'/'+family
    def storage(self,node_id,volume_id,instance_id,family,reservation_id=None):
        if family not in ('budget','drain','allocation','reservation'):raise ValueError('STORAGE_FAMILY')
        if family=='reservation':tail='reservations/'+_uuid(reservation_id)
        else:
            if reservation_id is not None:raise ValueError('UNEXPECTED_RESERVATION')
            tail=family
        return self.prefix+'storage/'+'/'.join(_uuid(v) for v in (node_id,volume_id,instance_id))+'/'+tail
    def original(self,request_id,command_hash,receipt_id):
        if type(command_hash) is not str or not _SHA.fullmatch(command_hash):raise ValueError('COMMAND_HASH')
        return dict(command=self.prefix+'commands/'+command_hash,receipt=self.prefix+'receipts/'+_uuid(receipt_id),
            publication=self.prefix+'publications/'+_uuid(request_id),outbox=self.prefix+'outbox/'+request_id,
            common_request=self.namespace+'/authority-v1/requests/'+request_id)
    def common_key(self,owner_id,actor_id,key):
        digest=hashlib.sha256(canonical(common_key_preimage(self.identity.cluster_id,owner_id,actor_id,key))).hexdigest()
        return self.namespace+'/authority-v1/command-keys/'+digest

@dataclass(frozen=True)
class NativePlanMeasure:
    operations: int
    encoded_bytes: int
    encoded_sha256: str

def measure_native_plan(operations):
    """Size only: no send, validation of domain semantics, permission or proof."""
    if type(operations) is not list or not 1<=len(operations)<=64:raise ValueError('OPERATION_CAP')
    raw=json.dumps(operations,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    if len(raw)>32768:raise ValueError('TRANSACTION_BYTE_CAP')
    return NativePlanMeasure(len(operations),len(raw),hashlib.sha256(raw).hexdigest())
