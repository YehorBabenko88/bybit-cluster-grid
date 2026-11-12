"""Opt-in bounded application-payload observations; no sender/store/authority.

The sink is separately owned and admitted. These local readbacks are not native
receipts, hard quotas, source authentication, or publication checkpoints.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time
import uuid

U63 = 2**63-1
KEYS = frozenset(('schema','instrument','producer_source_revision','source_kind',
    'endpoint','connection_id','observation_index','kind','received_at_utc',
    'received_monotonic_ns','payload_kind','payload_sha256','payload_bytes',
    'frame_metadata_sha256','previous_metadata_sha256','exchange_event_at_utc',
    'sequence','update_id','reason','publication'))
REASONS = {
    'frame': (None,), 'validated': (None,),
    'disconnect': ('transport_closed','transport_error','cancelled','normal_stop'),
    'gap_observation': ('sequence_invalid','buffer_pressure','frame_oversize',
        'restart_unknown','storage_failure','frame_invalid'),
    'resync': ('initial_snapshot','after_gap','source_restart'),
}

class RawCaptureError(RuntimeError):
    """Terminal refusal for an opted-in raw profile; never reconnect around it."""

def _need(value):
    if not value: raise RawCaptureError('RAW_CAPTURE_INVALID_OR_UNAVAILABLE')

def _match(value, pattern):
    return type(value) is str and re.fullmatch(pattern,value,re.ASCII) is not None

def _number(value, positive=False):
    _need(_match(value,r'0|[1-9][0-9]{0,18}'))
    _need(int(value)<=U63 and (not positive or int(value)>0))
    return value

def _sha(value, nullable=False):
    _need((nullable and value is None) or _match(value,r'[0-9a-f]{64}'))

def _utc(value):
    _need(_match(value,r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{3}Z'))
    try: dt=datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError: raise RawCaptureError('RAW_CAPTURE_INVALID_UTC') from None
    _need(dt.isoformat(timespec='milliseconds').replace('+00:00','Z')==value)
    return value

def _identity(value):
    _need(type(value) is dict and set(value)=={'exchange','category','symbol','instrument_version'})
    _need(value['exchange']=='bybit' and value['category']=='linear')
    _need(_match(value['symbol'],r'[A-Z0-9][A-Z0-9_-]{0,63}'))
    _number(value['instrument_version'],True)

def encode_observation(value):
    """Closed lexical/calendar/cross-field validation, independent of schema."""
    _need(type(value) is dict and set(value)==KEYS)
    _need(value['schema']=='grid.raw-capture-observation.v1-review1')
    _identity(value['instrument'])
    _need(_match(value['producer_source_revision'],r'[0-9a-f]{40}'))
    _need(value['source_kind'] in ('SYNTHETIC','PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED'))
    endpoint='synthetic://bybit/linear' if value['source_kind']=='SYNTHETIC' else 'wss://stream.bybit.com/v5/public/linear'
    _need(value['endpoint']==endpoint)
    _need(_match(value['connection_id'],r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'))
    _number(value['observation_index'],True); _number(value['received_monotonic_ns'])
    _utc(value['received_at_utc'])
    if value['exchange_event_at_utc'] is not None: _utc(value['exchange_event_at_utc'])
    for key in ('sequence','update_id'):
        if value[key] is not None: _number(value[key])
    for key in ('payload_sha256','frame_metadata_sha256','previous_metadata_sha256'): _sha(value[key],True)
    _number(value['payload_bytes']); _need(int(value['payload_bytes'])<=1048576)
    kind=value['kind']; _need(type(kind) is str and kind in REASONS)
    _need(value['reason'] in REASONS[kind] and value['publication']=='LOCAL_UNATTESTED')
    if kind=='frame':
        _need(value['payload_kind'] in ('TEXT_UTF8_REENCODED_NOT_WIRE','BINARY_APPLICATION_PAYLOAD'))
        _sha(value['payload_sha256'])
        _need(all(value[key] is None for key in ('frame_metadata_sha256','exchange_event_at_utc','sequence','update_id')))
    else:
        _need(value['payload_kind']=='NONE' and value['payload_sha256'] is None and value['payload_bytes']=='0')
    if kind in ('validated','resync'): _sha(value['frame_metadata_sha256'])
    try: raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,RecursionError): raise RawCaptureError('RAW_CAPTURE_INVALID_METADATA') from None
    _need(0<len(raw)<=16384)
    return raw

def decode_observation(raw):
    _need(type(raw) is bytes and 0<len(raw)<=16384)
    def pairs(items):
        out={}
        for key,value in items:
            _need(key not in out); out[key]=value
        return out
    def no_number(_): raise RawCaptureError('RAW_CAPTURE_NUMERIC_TOKEN')
    try: value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
                          parse_int=no_number,parse_float=no_number,parse_constant=no_number)
    except (ValueError,UnicodeError,RecursionError): raise RawCaptureError('RAW_CAPTURE_INVALID_METADATA') from None
    _need(encode_observation(value)==raw)
    return value

@dataclass(frozen=True)
class RawCaptureProfile:
    max_observations: int
    max_payload_bytes: int
    max_frame_bytes: int
    max_metadata_bytes: int
    reserved_control_slots: int

    def __post_init__(self):
        for value,limit in ((self.max_observations,16),(self.max_payload_bytes,4194304),
                (self.max_frame_bytes,1048576),(self.max_metadata_bytes,16384)):
            _need(type(value) is int and 0<value<=limit)
        _need(type(self.reserved_control_slots) is int and self.reserved_control_slots==2)
        _need(self.max_observations>self.reserved_control_slots)

@dataclass(frozen=True)
class FrameReference:
    metadata_sha256: str
    connection_id: str
    received_at_utc: str
    received_monotonic_ns: str
    _owner: object

def _clock():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),time.monotonic_ns()

class RawCaptureRecorder:
    def __init__(self,sink,*,instrument,producer_source_revision,source_kind,endpoint,
                 profile,clock=_clock,connection_id_factory=lambda:str(uuid.uuid4())):
        _need(isinstance(profile,RawCaptureProfile) and callable(clock) and callable(connection_id_factory))
        _identity(instrument)
        _need(callable(getattr(sink,'store_capture',None)))
        self.sink=sink; self.profile=profile; self._clock=clock; self._id_factory=connection_id_factory
        self._instrument=dict(instrument); self._revision=producer_source_revision
        self._source_kind=source_kind; self._endpoint=endpoint
        self._count=0; self._attempts=0; self._payload_charge=0; self._ordinal=0
        self._head=None; self._connection=None; self._connections=set(); self._refs={}; self._token=object()
        self._busy=False; self._failed=False; self._connected=False
        self._last_clock_ns=None
        self._last_received=None; self._last_raw=None; self._last_exchange=None
        self._gap_open=False; self._gap_durable=False; self._stop_reason=None
        self._gap_reason=None
        # Validate static fields without IO or consuming an observation.
        encode_observation(self._value('frame','00000000-0000-4000-8000-000000000000',1,
            ('2000-01-01T00:00:00.000Z','0'),b'',None,None,None,None,None))

    def matches(self,symbol,endpoint):
        return self._instrument['symbol']==symbol and self._endpoint==endpoint

    def _terminal(self,reason):
        self._failed=True; self._stop_reason=reason
        if not self._gap_open:
            self._gap_open=True; self._gap_durable=False; self._gap_reason=reason
        raise RawCaptureError('RAW_CAPTURE_STOP_'+reason.upper())

    def begin_connection(self):
        if self._failed or self._busy or self._connected: self._terminal('state')
        try:
            cid=self._id_factory()
            _need(_match(cid,r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'))
        except Exception: self._terminal('connection_identity')
        if cid in self._connections or len(self._connections)>=self.profile.max_observations: self._terminal('connection_identity')
        self._connections.add(cid); self._connection=cid; self._ordinal=0
        self._connected=True; self._refs.clear()

    def _now(self):
        try:
            stamp,mono=self._clock(); _utc(stamp)
            _need(type(mono) is int and 0<=mono<=U63)
            _need(self._last_clock_ns is None or mono>=self._last_clock_ns)
            self._last_clock_ns=mono
            return stamp,str(mono)
        except Exception: self._terminal('clock')

    def _value(self,kind,cid,index,received,payload,frame,exchange,sequence,update,reason):
        return dict(schema='grid.raw-capture-observation.v1-review1',instrument=dict(self._instrument),
            producer_source_revision=self._revision,source_kind=self._source_kind,endpoint=self._endpoint,
            connection_id=cid,observation_index=str(index),kind=kind,received_at_utc=received[0],
            received_monotonic_ns=received[1],payload_kind=('NONE' if payload is None else 'BINARY_APPLICATION_PAYLOAD'),
            payload_sha256=None if payload is None else hashlib.sha256(payload).hexdigest(),
            payload_bytes=str(0 if payload is None else len(payload)),frame_metadata_sha256=frame,
            previous_metadata_sha256=self._head,exchange_event_at_utc=exchange,sequence=sequence,
            update_id=update,reason=reason,publication='LOCAL_UNATTESTED')

    async def _emit(self,kind,*,received=None,payload=None,text=False,frame=None,
                    exchange=None,sequence=None,update=None,reason=None):
        if self._failed or self._busy or not self._connected: self._terminal('state')
        control=kind in ('gap_observation','disconnect')
        ceiling=self.profile.max_observations-(0 if control else self.profile.reserved_control_slots)
        if self._attempts>=ceiling: self._terminal('capacity')
        raw_count=0 if payload is None else len(payload)
        if self._payload_charge+raw_count>self.profile.max_payload_bytes: self._terminal('capacity')
        try:
            received=self._now() if received is None else received
            value=self._value(kind,self._connection,self._ordinal+1,received,payload,frame,exchange,sequence,update,reason)
            if text: value['payload_kind']='TEXT_UTF8_REENCODED_NOT_WIRE'
            raw=encode_observation(value); _need(len(raw)<=self.profile.max_metadata_bytes)
        except Exception: self._terminal('metadata')
        self._busy=True; self._attempts+=1; self._payload_charge+=raw_count
        try:
            facts=await self.sink.store_capture(observation_bytes=raw,payload_bytes=payload)
            _need(type(facts.observation_bytes) is bytes and facts.observation_bytes==raw)
            _need((facts.payload_bytes is None and payload is None) or
                  (type(facts.payload_bytes) is bytes and payload is not None and facts.payload_bytes==payload))
            _need(facts.observation_sha256==hashlib.sha256(raw).hexdigest())
            _need(type(facts.observation_byte_count) is int and facts.observation_byte_count==len(raw))
            _need(facts.payload_sha256==value['payload_sha256'])
            _need(type(facts.payload_byte_count) is int and facts.payload_byte_count==raw_count)
            _sha(facts.journal_record_digest)
            _need(facts.classification=='LOCAL_UNATTESTED' and facts.durability=='UNKNOWN')
            _need(facts.local_content_verified is True and facts.publication_confirmed is False
                  and facts.native_authority_verified is False and facts.replica_eligible is False)
            _need(not self._failed)
        except BaseException as error:
            self._failed=True; self._gap_open=True; self._gap_durable=False; self._stop_reason='storage_unknown'
            self._gap_reason='storage_failure'
            if not isinstance(error,Exception): raise
            raise RawCaptureError('RAW_CAPTURE_STORAGE_OUTCOME_UNKNOWN') from None
        finally: self._busy=False
        self._ordinal+=1; self._count+=1; self._head=hashlib.sha256(raw).hexdigest()
        return self._head,received

    async def frame(self,raw):
        if self._failed or self._busy: self._terminal('state')
        received=self._now(); self._last_received=received[0]
        try:
            _need(type(raw) in (str,bytes))
            if len(raw)>self.profile.max_frame_bytes:
                await self.gap('frame_oversize'); self._terminal('frame_oversize')
            payload=raw.encode('utf-8') if type(raw) is str else raw
        except RawCaptureError: raise
        except Exception: self._terminal('payload')
        if len(payload)>self.profile.max_frame_bytes:
            await self.gap('frame_oversize'); self._terminal('frame_oversize')
        if (self._attempts>=self.profile.max_observations-self.profile.reserved_control_slots
                or self._payload_charge+len(payload)>self.profile.max_payload_bytes):
            await self.gap('buffer_pressure'); self._terminal('capacity')
        sha,received=await self._emit('frame',received=received,payload=payload,text=type(raw) is str)
        ref=FrameReference(sha,self._connection,received[0],received[1],self._token)
        self._refs[sha]=ref; self._last_raw=self._now()[0]
        return ref

    def _reference(self,ref):
        if (type(ref) is not FrameReference or ref._owner is not self._token
                or ref.connection_id!=self._connection or self._refs.get(ref.metadata_sha256) is not ref):
            self._terminal('frame_reference')
        return ref.metadata_sha256,(ref.received_at_utc,ref.received_monotonic_ns)

    async def validated(self,ref,*,exchange_event_ms=None,sequence=None,update_id=None,resync=False,source_restart=False):
        frame,received=self._reference(ref)
        try:
            _need(type(resync) is bool and type(source_restart) is bool)
            def number(value):
                if value is None: return None
                _need(type(value) is int and 0<=value<=U63); return str(value)
            seq=number(sequence); update=number(update_id); exchange=None
            if exchange_event_ms is not None:
                number(exchange_event_ms)
                dt=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=exchange_event_ms)
                exchange=dt.isoformat(timespec='milliseconds').replace('+00:00','Z'); _utc(exchange)
        except Exception: self._terminal('exchange_fields')
        reason=('after_gap' if self._gap_open else 'source_restart' if source_restart else 'initial_snapshot') if resync else None
        await self._emit('resync' if resync else 'validated',received=received,frame=frame,
                         exchange=exchange,sequence=seq,update=update,reason=reason)
        if exchange is not None: self._last_exchange=max(self._last_exchange or exchange,exchange)
        if resync: self._gap_open=False; self._gap_durable=False

    async def gap(self,reason,ref=None):
        self._gap_open=True; self._gap_durable=False; self._gap_reason=reason
        frame,received=(None,None) if ref is None else self._reference(ref)
        await self._emit('gap_observation',received=received,frame=frame,reason=reason)
        self._gap_durable=True

    async def disconnect(self,reason):
        if not self._connected: return False
        if self._failed:
            self._connected=False; return False
        try:
            await self._emit('disconnect',reason=reason)
            if reason!='normal_stop':
                self._gap_open=True; self._gap_durable=True; self._gap_reason=reason
            return True
        finally: self._connected=False

    def metrics(self):
        return dict(last_frame_received_utc=self._last_received,last_raw_readback_utc=self._last_raw,
            last_validated_exchange_utc=self._last_exchange,last_observation_readback_sha256=self._head,
            observations_stored=self._count,observation_attempts=self._attempts,
            payload_occurrence_bytes=self._payload_charge,gap_open=self._gap_open,
            gap_durable=self._gap_durable,gap_reason=self._gap_reason,failed=self._failed,stop_reason=self._stop_reason,
            publication='LOCAL_UNATTESTED',physical_hard_quota='UNQUALIFIED')
