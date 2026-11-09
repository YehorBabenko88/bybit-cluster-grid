"""Direct disposable target only. No scheduler, authenticated submit or publication.

Trusted commissioning chooses two source repositories and an OWN temporary root.
Local context is test-call custody, NOT a Windows identity or native authority.
Journal is the existing local receipt primitive, never an experiment registry.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time
import types
import uuid

from .journal import Journal

REQUEST_SCHEMA='unified.gateway.target-request.v1'
RESULT_SCHEMA='unified.gateway.direct-target-result.v1'
CAPABILITY='meta.ohlcv.untouched_levels.v1'
STRATT_HEAD='aed8a7c8a952f96803c207d5e90b133969a47f04'
STRATT_MODULE_SHA='689bd82be39cdc15725fcefbe2cefc248c4feb51c27822f9813558f5587e81dd'
META_HEAD='f3c01a23fa5baaeeeb28eb8e9397e72b5ef4d5a1'
DATASET_SHA='33d5bf0f918884c8908795b384e0964a48a1351c808800964b8cacf3f83e28b6'
RESEARCH_SHA='c548e2ffcd542d5d741682303694b3c6d06507740f158a6e30089b2d5355f648'
EXPECTED_ARTIFACT_SHA='f4997d7d26211676cd8664e53d7999f8b71f203510f3b9a275b439c403e03940'
EXPECTED_DESCRIPTOR_SHA='664d34f06721b3d62404ea2f05b6b929a59b9e3eeecc281a71d2ca927c802cda'
LOCAL_PRINCIPAL='11111111-1111-4111-8111-111111111111'
BUDGET={'max_input_bytes':16384,'max_output_bytes':16384,'max_rows':3,'max_executions':1}
_MARKER=b'unified.direct-target.owned-disposable.v1\n'


class TargetRejected(ValueError):pass


def _need(value,code='TARGET_CONTRACT_REJECTED'):
    if not value:raise TargetRejected(code)


def _canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    result={}
    for key,value in pairs:
        _need(key not in result);result[key]=value
    return result


def _decode(raw):
    _need(type(raw) is bytes and 0<len(raw)<=16384)
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(TargetRejected('TARGET_CONTRACT_REJECTED')))
        _need(_canonical(value)==raw)
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):
        raise TargetRejected('TARGET_CONTRACT_REJECTED') from None


def template_request():
    """Fixed data-only template; its fields issue no authority or permission."""
    return dict(schema=REQUEST_SCHEMA,request_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        target_kind='MetaAnalyse',target_capability=CAPABILITY,target_version=META_HEAD,
        dataset_manifest_id='local-sha256:'+DATASET_SHA,dataset_revision='LOCAL_FIXTURE_1',
        experiment_id='fixture.gateway.btc.levels',strategy_version=None,parameters_digest=RESEARCH_SHA,
        execution_mode='DIRECT_DISPOSABLE_SYNTHETIC',resource_budget=copy.deepcopy(BUDGET),
        quota_owner='LOCAL_TEST_ONLY',principal_id=LOCAL_PRINCIPAL,authority_generation=None,
        assignment_revision=None,fencing_token=None,idempotency_key='fixed-btc-three-row-1',
        result_schema=RESULT_SCHEMA,result_artifact_ref=None)


class _Prepared:
    __slots__=('raw',)
    def __init__(self,raw):self.raw=raw


def prepare_target(raw):
    value=_decode(raw);expected=template_request()
    _need(type(value) is dict and set(value)==set(expected))
    for name in expected.keys()-{'request_id','idempotency_key'}:
        # Canonical bytes enforce bool/int and nested exact types, no Python == alias.
        _need(_canonical(value[name])==_canonical(expected[name]))
    for name in ('request_id',):
        _need(type(value[name]) is str and re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}',value[name]) is not None)
    for name in ('idempotency_key','experiment_id'):
        _need(type(value[name]) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',value[name]) is not None)
    return _Prepared(raw)


def public_submit(_request):raise TargetRejected('PUBLIC_SUBMIT_DENY')


def capability_registry():
    rows=[]
    for repo,kind in [('strattester','historical_backtest'),('strattester','historical_replay'),
                      ('math','statistical_computation'),('meta_analyse',CAPABILITY),
                      ('UNRESOLVED','trader_intelligence.offline_reconstruction')]:
        active=kind==CAPABILITY
        rows.append(dict(owning_repository=repo,capability=kind,
            availability='DIRECT_DISPOSABLE_ONLY' if active else 'UNAVAILABLE',
            entrypoint='strattester.research.gateway_adapter.execute_synthetic_research -> meta_analyse.ohlcv_research_adapter.analyze_ohlcv_research' if active else None,
            input_schema='stratt.gateway.synthetic.research.request.v1-review1' if active else None,
            output_schema='meta.ohlcv.research.result.v1' if active else None,
            dataset='local-sha256:'+DATASET_SHA if active else None,
            resource_budget=copy.deepcopy(BUDGET) if active else None,
            authority_scope='LOCAL_TEST_SCOPE_NOT_AUTHENTICATED' if active else None,
            cancellation='COOPERATIVE_DISCARD_BEFORE_RESULT_COMMIT' if active else 'UNAVAILABLE',
            recovery='ORIGINAL_INTENT_UNKNOWN_NO_REEXECUTION' if active else 'UNAVAILABLE',
            scheduler_admission='BLOCKED',limitations=['NO_NATIVE_CPU_RSS_CONTAINMENT','NO_SCHEDULER_OR_PUBLICATION','SYNTHETIC_LOCAL_ONLY'] if active else ['NOT_QUALIFIED_FOR_THIS_ADAPTER']))
    return rows


class _LocalContext:
    __slots__=()


class DisposableTargetStand:
    """Exclusive own temporary workspace. Not a hostile-local-admin sandbox.

    Only fixed pinned source is executed. Trusted commissioning owns directory
    ACL/custody and Python/dependencies; source hashes do not authenticate code.
    The small fixed workload is in-process/cooperative, NOT a CPU/RSS guarantee.
    """
    def __init__(self,root,*,stratt_source_root,meta_source_root):
        self.root=Path(root).absolute();self.stratt_source_root=stratt_source_root;self.meta_source_root=meta_source_root
        self._contexts=[];self._cancelled=set();self._mutex=threading.Lock();self._decision_lock=threading.Lock();self._closed=True;self.invocations=0
        self._lock=None
        try:
            for path in (self.root,*self.root.parents):
                s=path.lstat();_need(stat.S_ISDIR(s.st_mode) and not getattr(s,'st_file_attributes',0)&1024 and not path.is_symlink())
            names={p.name for p in self.root.iterdir()}
            _need(names<= {'stand.marker','stand.lock','direct-journal.db'})
            marker=self.root/'stand.marker'
            if names:_need(marker.read_bytes()==_MARKER)
            else:
                with marker.open('xb') as stream:stream.write(_MARKER)
            self._lock=(self.root/'stand.lock').open('a+b')
            info=os.fstat(self._lock.fileno());_need(info.st_nlink==1 and not getattr(info,'st_file_attributes',0)&1024)
            if info.st_size==0:self._lock.write(b'0');self._lock.flush()
            self._lock.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self._lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            path=self.root/'direct-journal.db'
            if path.exists():
                info=path.lstat();_need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not getattr(info,'st_file_attributes',0)&1024 and info.st_size<=2097152)
            self._journal=Journal(path);self._journal.initialize();self._records();self._closed=False
        except BaseException:
            if self._lock:self._lock.close()
            raise TargetRejected('DISPOSABLE_STAND_UNAVAILABLE') from None

    def close(self):
        with self._mutex:
            self._closed=True
            for state in self._contexts:state[3].set()
            if self._lock:self._lock.close();self._lock=None

    def local_test_context(self,*,scope='DIRECT_TARGET',lifetime_seconds=60):
        _need(not self._closed and type(scope) is str and type(lifetime_seconds) is int and 0<=lifetime_seconds<=60 and len(self._contexts)<32)
        ctx=_LocalContext();self._contexts.append((ctx,scope,time.monotonic()+lifetime_seconds,threading.Event()));return ctx

    def revoke(self,context):
        with self._decision_lock:
            state=next((state for state in self._contexts if context is state[0]),None)
            _need(state is not None);state[3].set()

    def cancel(self,request_id):
        with self._decision_lock:
            _need(type(request_id) is str and len(request_id)<=36 and len(self._cancelled)<64)
            self._cancelled.add(request_id)

    def _check(self,context):
        state=next((state for state in self._contexts if context is state[0]),None)
        _need(not self._closed and type(context) is _LocalContext and state is not None
              and not state[3].is_set() and state[1]=='DIRECT_TARGET' and time.monotonic()<state[2],'LOCAL_TEST_SCOPE_DENIED')

    def _records(self):
        _need(self._journal.path.stat().st_size<=2097152)
        records=self._journal.read();_need(len(records)<=64)
        for row in records:
            receipt=row['receipt'];_need(type(receipt) is dict and receipt.get('schema')=='unified.direct-target.journal.v1')
            _need(set(receipt)=={'schema','request_raw','request_sha256','phase','result_raw','result_sha256'})
            original=receipt['request_raw'].encode('ascii');prepare_target(original);_need(_sha(original)==receipt['request_sha256'])
            _need(receipt['phase'] in ('STARTED','FINISHED'))
            if receipt['phase']=='STARTED':_need(receipt['result_raw'] is None and receipt['result_sha256'] is None)
            else:
                result=receipt['result_raw'].encode('ascii');_need(_sha(result)==receipt['result_sha256']);_decode(result)
        return records

    def _append(self,raw,phase,result=None):
        records=self._records();_need(len(records)<64,'LOCAL_JOURNAL_CAPACITY')
        data=None if result is None else _canonical(result)
        self._journal.append('OBSERVING',dict(schema='unified.direct-target.journal.v1',request_raw=raw.decode('ascii'),
            request_sha256=_sha(raw),phase=phase,result_raw=None if data is None else data.decode('ascii'),
            result_sha256=None if data is None else _sha(data)),expected_sequence=len(records))

    def _git_raw(self,path):
        _need(type(self.stratt_source_root) is str and Path(self.stratt_source_root).is_absolute())
        return subprocess.check_output(['git','--no-replace-objects','-C',self.stratt_source_root,'show',STRATT_HEAD+':'+path],timeout=10,stderr=subprocess.PIPE)

    def _invoke(self,cancelled):
        code=self._git_raw('strattester/research/gateway_adapter.py');_need(_sha(code)==STRATT_MODULE_SHA,'TARGET_SOURCE_UNAVAILABLE')
        raw=self._git_raw('docs/gateway/research/evidence/btc-v1/request.json');_need(_sha(raw)==RESEARCH_SHA,'TARGET_INPUT_UNAVAILABLE')
        payload=json.loads(raw)['payload'];_need(_sha(_canonical(payload))==DATASET_SHA,'TARGET_DATASET_UNAVAILABLE')
        module=types.ModuleType('_unified_fixed_target');exec(compile(code,'pinned-stratt-gateway-adapter','exec'),module.__dict__)
        self.invocations+=1
        return module.execute_synthetic_research(raw,meta_source_root=self.meta_source_root,cancel_check=cancelled)

    def _envelope(self,q,raw,status,result=None,error=None):
        artifact=None if result is None else result['artifact_bytes']
        return dict(schema=RESULT_SCHEMA,status=status,request_id=q['request_id'],request_sha256=_sha(raw),
            target_capability=CAPABILITY,target_version=META_HEAD,experiment_id=q['experiment_id'],
            dataset={'manifest_id':q['dataset_manifest_id'],'revision':q['dataset_revision'],'raw_sha256':DATASET_SHA,'kind':'FIXED_SYNTHETIC_LOCAL_NOT_A4_MANIFEST'},
            parameters_digest=q['parameters_digest'],execution_mode=q['execution_mode'],resource_budget=copy.deepcopy(BUDGET),
            result=None if artifact is None else json.loads(artifact),research_descriptor=None if result is None else result['descriptor'],
            result_artifact_ref=None if artifact is None else {'kind':'LOCAL_UNATTESTED_SHA256','sha256':_sha(artifact),'byte_count':str(len(artifact))},
            publication_status='LOCAL_UNATTESTED',execution_authority=False,scheduler_admission='BLOCKED',
            authenticated_gateway=False,physical_acceptance=False,error=error,
            provenance={'stratt_head':STRATT_HEAD,'stratt_module_sha256':STRATT_MODULE_SHA,'meta_head':META_HEAD,'research_input_sha256':RESEARCH_SHA},
            limitations=['LOCAL_TEST_SCOPE_NOT_AUTHENTICATED','NO_NATIVE_RESOURCE_CONTAINMENT','NO_REPLICA_OR_PUBLICATION_PROOF','NO_ORDERS_NO_LEDGER','WHOLE_WINDOW_NOT_HISTORICAL_SIGNAL'])

    def execute(self,prepared,*,context):
        self._check(context);_need(type(prepared) is _Prepared)
        raw=prepare_target(prepared.raw).raw;q=_decode(raw)
        with self._mutex:
            self._check(context)
            try:
                records=self._records();matches=[]
                for row in records:
                    r=row['receipt'];prior=_decode(r['request_raw'].encode('ascii'))
                    if prior['request_id']==q['request_id'] or prior['idempotency_key']==q['idempotency_key']:
                        _need(r['request_raw'].encode('ascii')==raw,'IDEMPOTENCY_COLLISION');matches.append(r)
                if matches:
                    last=matches[-1]
                    return _decode(last['result_raw'].encode('ascii')) if last['phase']=='FINISHED' else self._envelope(q,raw,'UNKNOWN',error='ORIGINAL_INTENT_OUTCOME_UNKNOWN_NO_REEXECUTION')
                self._append(raw,'STARTED')
                def cancelled():
                    self._check(context)
                    return q['request_id'] in self._cancelled
                if cancelled():result=self._envelope(q,raw,'CANCELLED',error='LOCAL_CANCELLED')
                else:
                    try:
                        actual=self._invoke(cancelled)
                        _need(type(actual) is dict and set(actual)=={'descriptor','artifact_bytes'})
                        artifact=actual['artifact_bytes'];_need(type(artifact) is bytes and 0<len(artifact)<=8192)
                        decoded=_decode(artifact)
                        _need(decoded['units']=={'price':'USDT/BTC','volume':'BTC'} and decoded['execution_authority'] is False)
                        _need(actual['descriptor']['artifact']['raw_sha256']==_sha(artifact))
                        _need(actual['descriptor']['artifact']['byte_count']==str(len(artifact)))
                        # Fixed-profile independent golden bytes: JSON Schema
                        # numeric equality does not prove canonical byte identity.
                        _need(_sha(artifact)==EXPECTED_ARTIFACT_SHA and
                              _sha(_canonical(actual['descriptor']))==EXPECTED_DESCRIPTOR_SHA)
                        result=self._envelope(q,raw,'CANCELLED',error='LOCAL_CANCELLED') if cancelled() else self._envelope(q,raw,'DIRECT_TARGET_PASS',actual)
                    except Exception as error:
                        code=getattr(error,'code',None)
                        status=('CANCELLED' if code=='CANCELLED' else 'UNKNOWN'
                                if (isinstance(error,TargetRejected) and str(error)=='LOCAL_TEST_SCOPE_DENIED')
                                or (code is None and not isinstance(error,(TargetRejected,subprocess.SubprocessError,OSError))) else 'FAILED')
                        result=self._envelope(q,raw,status,error='LOCAL_CANCELLED' if status=='CANCELLED' else 'TARGET_RESULT_UNAVAILABLE')
                with self._decision_lock:
                    # Local cancellation/revocation and final Journal commit have
                    # one ordering. This is not distributed commit-time fencing.
                    self._check(context)
                    if q['request_id'] in self._cancelled:result=self._envelope(q,raw,'CANCELLED',error='LOCAL_CANCELLED')
                    _need(len(_canonical(result))<=16384)
                    self._append(raw,'FINISHED',result)
                return result
            except TargetRejected:raise
            except Exception:raise TargetRejected('LOCAL_JOURNAL_OR_RESULT_UNAVAILABLE') from None
