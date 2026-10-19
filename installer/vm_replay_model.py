"""PURE MEMORY protocol model. Durable storage, authority and recovery NOT IMPLEMENTED."""
from dataclasses import dataclass,asdict,replace
import hashlib
import json
import threading
from installer.vm_lab_json import canonical,check_value,load
from installer.vm_lab_plan import CASES,_shape,_need,_guid,_digest


class ModelCrash(RuntimeError):pass


@dataclass(frozen=True)
class Record:
    nonce:str;binding:str;key_epoch:int;policy_epoch:int;expires:int
    status:str='ISSUED';fence:int=0;claimant:str='';until:int=0;evidence:str=''


@dataclass(frozen=True)
class Image:
    revision:int=0;counter:int=0;key_epoch:int=1;policy_epoch:int=1;clock:int=0
    records:tuple=()


@dataclass(frozen=True)
class Witness:
    revision:int;image_sha256:str


@dataclass(frozen=True)
class Checkpoint:
    image:Image;witness:Witness


@dataclass(frozen=True)
class Claim:
    nonce:str;binding:str;claimant:str;fence:int;key_epoch:int;policy_epoch:int


@dataclass(frozen=True)
class AssumedValidation:
    """Model event assumption, NOT cryptographic validation or an authority receipt."""
    context:Claim;evidence:str;roles:tuple


def _fingerprint(image):
    return hashlib.sha256(json.dumps(asdict(image),sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest()


def _valid_image(image):
    _need(type(image) is Image,'VM_MODEL_RECOVERY_UNCERTAIN')
    for name in ('revision','counter','clock','key_epoch','policy_epoch'):
        v=getattr(image,name)
        _need(type(v) is int and (1 if name in ('key_epoch','policy_epoch') else 0)<=v<2**63,'VM_MODEL_RECOVERY_UNCERTAIN')
    _need(type(image.records) is tuple and len(image.records)<=64 and image.counter==len(image.records) and image.revision>=image.counter,'VM_MODEL_RECOVERY_UNCERTAIN')
    nonces=[]
    for r in image.records:
        _need(type(r) is Record,'VM_MODEL_RECOVERY_UNCERTAIN')
        _digest(r.nonce);_digest(r.binding);nonces.append(r.nonce)
        for name in ('key_epoch','policy_epoch','expires','fence','until'):
            v=getattr(r,name);_need(type(v) is int and 0<=v<2**63,'VM_MODEL_RECOVERY_UNCERTAIN')
        _need(1<=r.key_epoch<=image.key_epoch and 1<=r.policy_epoch<=image.policy_epoch and r.expires>0,'VM_MODEL_RECOVERY_UNCERTAIN')
        _need(r.status in ('ISSUED','CLAIMED','CONSUMED'),'VM_MODEL_RECOVERY_UNCERTAIN')
        if r.status=='ISSUED':
            _need(r.fence==0 and r.claimant=='' and r.until==0 and r.evidence=='','VM_MODEL_RECOVERY_UNCERTAIN')
        else:
            _guid(r.claimant);_need(r.fence>=1 and 0<r.until<=r.expires,'VM_MODEL_RECOVERY_UNCERTAIN')
            if r.status=='CONSUMED':_digest(r.evidence)
            else:_need(r.evidence=='','VM_MODEL_RECOVERY_UNCERTAIN')
    _need(len(set(nonces))==len(nonces),'VM_MODEL_RECOVERY_UNCERTAIN')


def _claim_context(claim):
    _need(type(claim) is Claim,'VM_MODEL_VALIDATION_ASSUMPTION_REQUIRED')
    _digest(claim.nonce);_digest(claim.binding);_guid(claim.claimant)
    _need(all(type(v) is int and 1<=v<2**63 for v in (claim.fence,claim.key_epoch,claim.policy_epoch)),'VM_MODEL_FENCE')


def _binding(value):
    check_value(value);_shape(value,'audience plan_sha256 image_sha256 code_sha256 artifact_sha256 host_id vm_id session_id policy_epoch')
    _need(value['audience']=='VM_LAB_TEST_ONLY','VM_MODEL_AUDIENCE')
    for key in ('plan_sha256','image_sha256','code_sha256','artifact_sha256'):_digest(value[key])
    _guid(value['host_id']);_guid(value['vm_id']);_guid(value['session_id'])
    _need(type(value['policy_epoch']) is int and 1<=value['policy_epoch']<2**63,'VM_MODEL_POLICY')
    return hashlib.sha256(canonical(value)).hexdigest()


class ReplayModel:
    """Abstract transactions and independent witness are ASSUMED, never real I/O."""
    def __init__(self):
        self._lock=threading.Lock();self._image=Image()
        self._witness=Witness(0,_fingerprint(self._image));self._anchor=self._witness;self._dead=False

    @property
    def revision(self):return self._image.revision
    @property
    def anchor(self):return self._anchor
    def checkpoint(self):
        with self._lock:return Checkpoint(self._image,self._witness)

    @classmethod
    def recover(cls,checkpoint,anchor):
        _need(type(checkpoint) is Checkpoint and type(anchor) is Witness,'VM_MODEL_RECOVERY_UNCERTAIN')
        image=checkpoint.image
        _need(type(image) is Image and type(checkpoint.witness) is Witness,'VM_MODEL_RECOVERY_UNCERTAIN')
        try:
            _valid_image(image);_digest(anchor.image_sha256);_digest(checkpoint.witness.image_sha256)
            _need(type(anchor.revision) is int and type(checkpoint.witness.revision) is int,'VM_MODEL_RECOVERY_UNCERTAIN')
        except ValueError:raise ValueError('VM_MODEL_RECOVERY_UNCERTAIN') from None
        _need(checkpoint.witness==anchor and anchor.revision==image.revision and
              anchor.image_sha256==_fingerprint(image),'VM_MODEL_RECOVERY_UNCERTAIN')
        result=cls();result._image=image;result._witness=anchor;result._anchor=anchor
        return result

    def _check(self,now,trusted_now,expected):
        _need(not self._dead,'VM_MODEL_PROCESS_CRASHED')
        _need(type(now) is int and type(trusted_now) is int and 0<=now<2**63-60 and 0<=trusted_now<2**63-60,'VM_MODEL_CLOCK')
        _need(abs(now-trusted_now)<=2 and now>=self._image.clock,'VM_MODEL_CLOCK_DRIFT')
        _need(type(expected) is int and expected==self._image.revision,'VM_MODEL_CAS_FENCED')

    def _commit(self,image,now,crash):
        _need(crash in (None,'before_prepare','after_prepare','after_commit','after_ack','torn_commit'),'VM_MODEL_FAULT_INVALID')
        if crash in ('before_prepare','after_prepare'):
            self._dead=True;raise ModelCrash('VM_MODEL_PRECOMMIT_CRASH')
        _need(self._image.revision<2**63-1,'VM_MODEL_BUDGET')
        new=replace(image,revision=self._image.revision+1,clock=now)
        _valid_image(new)
        witness=Witness(new.revision,_fingerprint(new))
        # Abstract atomic durable commit + independent monotonic anchor is an
        # explicit MODEL AXIOM. No physical atomicity/durability is implemented.
        if crash=='torn_commit':
            self._image=new;self._anchor=witness;self._dead=True
            raise ModelCrash('VM_MODEL_TORN_COMMIT')
        self._image,self._witness,self._anchor=new,witness,witness
        if crash in ('after_commit','after_ack'):
            self._dead=True;raise ModelCrash('VM_MODEL_POSTCOMMIT_CRASH')

    def issue(self,binding,role,now,trusted_now,expected,crash=None):
        binding=load(canonical(binding).decode('ascii'));digest=_binding(binding)
        with self._lock:
            self._check(now,trusted_now,expected)
            _need(type(role) is str and role=='issuer','VM_MODEL_ISSUER_ROLE')
            _need(binding['policy_epoch']==self._image.policy_epoch,'VM_MODEL_POLICY')
            _need(len(self._image.records)<64,'VM_MODEL_BUDGET')
            counter=self._image.counter+1
            nonce=hashlib.sha256(canonical({'counter':counter,'binding':digest})).hexdigest()
            record=Record(nonce,digest,self._image.key_epoch,self._image.policy_epoch,now+60)
            self._commit(replace(self._image,counter=counter,records=self._image.records+(record,)),now,crash)
            return nonce

    def _record(self,nonce):
        _digest(nonce)
        records={r.nonce:r for r in self._image.records}
        _need(nonce in records,'VM_MODEL_UNKNOWN_CHALLENGE')
        return records[nonce]

    def _replace_record(self,record):
        return replace(self._image,records=tuple(record if r.nonce==record.nonce else r for r in self._image.records))

    def _epoch(self,record,now):
        _need(record.key_epoch==self._image.key_epoch and record.policy_epoch==self._image.policy_epoch,'VM_MODEL_EPOCH_REVOKED')
        _need(now<record.expires,'VM_MODEL_CHALLENGE_EXPIRED')

    def claim(self,nonce,claimant,binding,now,trusted_now,expected,crash=None):
        binding=load(canonical(binding).decode('ascii'));digest=_binding(binding);_guid(claimant)
        with self._lock:
            self._check(now,trusted_now,expected);record=self._record(nonce);self._epoch(record,now)
            _need(record.binding==digest,'VM_MODEL_BINDING')
            _need(record.status=='ISSUED' or (record.status=='CLAIMED' and now>=record.until),'VM_MODEL_ALREADY_CLAIMED')
            new=replace(record,status='CLAIMED',fence=record.fence+1,claimant=claimant,until=min(now+5,record.expires))
            self._commit(self._replace_record(new),now,crash)
            return Claim(nonce,digest,claimant,new.fence,new.key_epoch,new.policy_epoch)

    def consume(self,claim,validation,now,trusted_now,expected,crash=None):
        _need(type(claim) is Claim and type(validation) is AssumedValidation,'VM_MODEL_VALIDATION_ASSUMPTION_REQUIRED')
        _digest(validation.evidence);_claim_context(claim);_claim_context(validation.context)
        _need(type(validation.roles) is tuple and all(type(role) is str for role in validation.roles),'VM_MODEL_VALIDATION_FAILED')
        _need(all(type(v) is int and 1<=v<2**63 for v in (claim.fence,claim.key_epoch,claim.policy_epoch)),'VM_MODEL_FENCE')
        with self._lock:
            self._check(now,trusted_now,expected);record=self._record(claim.nonce);self._epoch(record,now)
            _need(record.status=='CLAIMED' and now<record.until,'VM_MODEL_CLAIM_EXPIRED_OR_CONSUMED')
            _need((claim.binding,claim.claimant,claim.fence,claim.key_epoch,claim.policy_epoch)==
                  (record.binding,record.claimant,record.fence,record.key_epoch,record.policy_epoch),'VM_MODEL_FENCE')
            _need(validation.context==claim and validation.roles==('observer','approval'),'VM_MODEL_VALIDATION_FAILED')
            self._commit(self._replace_record(replace(record,status='CONSUMED',evidence=validation.evidence)),now,crash)
            return self.report()

    def rotate(self,role,now,trusted_now,expected,crash=None):
        with self._lock:
            self._check(now,trusted_now,expected);_need(type(role) is str and role=='policy-authority','VM_MODEL_POLICY_ROLE')
            self._commit(replace(self._image,key_epoch=self._image.key_epoch+1,policy_epoch=self._image.policy_epoch+1),now,crash)

    def report(self):
        return {'status':'BLOCKED','mode':'MODEL_ONLY','durable_storage':'NOT_IMPLEMENTED','authentication':'MODEL_ASSUMPTION',
                'execution_authorized':False,'physical_ready':False,'readiness_passed':False,'verified_safety_cases':0,
                'negative_cases':[{'case':name,'execution':'NOT_RUN','assurance':'BLOCKED_UNPROVEN'} for name,_ in CASES],
                'blockers':['ATOMIC_DURABILITY_ASSUMED','INDEPENDENT_NONROLLBACK_ANCHOR_ASSUMED',
                            'AUTHORITY_AND_CLOCK_ASSUMED','DETERMINISTIC_NONCES_NOT_CSPRNG',
                            'REAL_OBSERVER_AND_PRINCIPAL_PROOF_ABSENT','ACL_NAMESPACE_ABA','GLOBAL_KERNEL_EXHAUSTION']}
