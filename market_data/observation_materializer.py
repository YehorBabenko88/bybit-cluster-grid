"""Pure current-v2 WS observation-window replay into candidate minute v1.2.

This is not a writer, incremental checkpoint, committed ACK or source admission.
The full original contiguous window must remain available for replay; its pending
subset is not independently resumable. Numeric accumulation belongs to Math via
FootprintBuilder, and minute representation belongs to the existing v1.2 codec.
"""
from dataclasses import dataclass,field
from datetime import datetime
from decimal import Decimal
import hashlib,json,re
from .raw_capture import decode_observation,RawCaptureError
from .public_trades import decode_frame,parse_trades,delivery_identity,execution_record
from .timestamp_codec import epoch_milliseconds_from_utc
from .history_contract import _snapshot_json,_clock,_units
from .footprint_state import FootprintBuilder
from .provenance import minute_record_v12,canonical

@dataclass(frozen=True,slots=True)
class RawObservation:
    observation_bytes:bytes
    payload_bytes:bytes|None

@dataclass(frozen=True,slots=True)
class ObservationChainAnchor:
    connection_id:str
    next_observation_index:int
    previous_metadata_sha256:str|None

@dataclass(frozen=True,slots=True)
class ObservationState:
    observation_index:int
    metadata_sha256:str
    kind:str
    classification:str
    reasons:tuple[str,...]=()

@dataclass(frozen=True,slots=True)
class PendingExecution:
    delivery_key:str
    content_sha256:str
    execution_bytes:bytes
    frame_metadata_sha256:str
    validated_metadata_sha256:str
    reason:str

@dataclass(frozen=True,slots=True)
class MinuteObservationDependency:
    observation_index:int
    metadata_sha256:str
    kind:str
    received_at_ms:int
    payload_sha256:str|None

@dataclass(frozen=True,slots=True)
class MaterializedMinute:
    record_bytes:bytes
    record_fingerprint:str
    frame_metadata_sha256s:tuple[str,...]
    validated_metadata_sha256s:tuple[str,...]
    delivery_keys:tuple[str,...]
    dependencies:tuple[MinuteObservationDependency,...]
    availability_components:tuple[tuple[str,int],...]
    input_sha256:str

@dataclass(frozen=True,slots=True)
class AdvisoryObservationCursor:
    last_observation_index:int
    last_metadata_sha256:str
    next_observation_index:int|None
    window_sha256:str
    advisory_only:bool=field(default=True,init=False)
    durable_acknowledgement:bool=field(default=False,init=False)
    independently_resumable:bool=field(default=False,init=False)

@dataclass(frozen=True,slots=True)
class MaterializedObservationWindow:
    input_sha256:str
    window_sha256:str
    anchor:ObservationChainAnchor
    window:tuple[RawObservation,...]
    observation_states:tuple[ObservationState,...]
    minutes:tuple[MaterializedMinute,...]
    pending:tuple[RawObservation,...]
    pending_observation_indices:tuple[int,...]
    pending_executions:tuple[PendingExecution,...]
    advisory_cursor:AdvisoryObservationCursor
    schema:str=field(default='market_data.observation-minute-window.v1',init=False)
    coverage:str=field(default='PARTIAL',init=False)
    publication:str=field(default='LOCAL_UNATTESTED',init=False)
    source_authentication:str=field(default='NOT_EVALUATED',init=False)
    availability_policy:str=field(default='CONSERVATIVE_MAX_DECLARED_RECEIVE_FINALIZATION_INGESTION_NOT_COMMIT_OR_PIT',init=False)
    pending_subset_independently_resumable:bool=field(default=False,init=False)
    execution_authority:bool=field(default=False,init=False)
    trading_authorized:bool=field(default=False,init=False)

_ENDPOINTS={'PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED':'wss://stream.bybit.com/v5/public/linear','SYNTHETIC':'synthetic://bybit/linear'}
_UUID='[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
_U63=2**63-1

def _hash(raw):return hashlib.sha256(raw).hexdigest()
def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def _text(value,pattern):
    if type(value) is not str or re.fullmatch(pattern,value,re.ASCII) is None:raise ValueError('OBSERVATION_LITERAL_DECLARATION_REQUIRED')
    return value

def _capture(window,anchor,tick,parameters):
    if (type(window) is not tuple and type(window) is not list) or not 1<=len(window)<=16:raise ValueError('OBSERVATION_BOUNDED_FULL_WINDOW_REQUIRED')
    if type(anchor) is not ObservationChainAnchor:raise ValueError('OBSERVATION_LITERAL_CHAIN_ANCHOR_REQUIRED')
    # Capture ALL records and parameters before decoder/parser/Math callbacks.
    copies=[];total_payload=0
    for item in tuple(window):
        if type(item) is not RawObservation:raise ValueError('OBSERVATION_EXACT_RAW_RECORD_REQUIRED')
        raw,payload=item.observation_bytes,item.payload_bytes
        if type(raw) is not bytes or not 0<len(raw)<=16384 or payload is not None and type(payload) is not bytes:raise ValueError('OBSERVATION_IMMUTABLE_BYTES_REQUIRED')
        count=0 if payload is None else len(payload)
        if count>1048576:raise ValueError('OBSERVATION_FRAME_BYTE_BUDGET')
        total_payload+=count
        if total_payload>4194304:raise ValueError('OBSERVATION_WINDOW_PAYLOAD_BUDGET')
        copies.append(RawObservation(raw,payload))
    anchor_values=(anchor.connection_id,anchor.next_observation_index,anchor.previous_metadata_sha256)
    parameters,anchor_values=_snapshot_json((parameters,anchor_values),max_bytes=65536)
    if type(tick) is not Decimal or not tick.is_finite():raise ValueError('OBSERVATION_PLAIN_FINITE_DECIMAL_TICK_REQUIRED')
    parts=tick.as_tuple()
    if len(parts.digits)>128 or not -4096<=parts.exponent<=4096:raise ValueError('OBSERVATION_TICK_RESOURCE_BUDGET')
    connection,next_index,previous=anchor_values
    _text(connection,_UUID)
    if type(next_index) is not int or not 1<=next_index<=_U63 or next_index+len(copies)-1>_U63:raise ValueError('OBSERVATION_CHAIN_INDEX_REQUIRED')
    if previous is not None:_text(previous,'[0-9a-f]{64}')
    if next_index>1 and previous is None:raise ValueError('OBSERVATION_EXPLICIT_PREDECESSOR_REQUIRED')
    return tuple(copies),ObservationChainAnchor(connection,next_index,previous),tick,parameters

def materialize_observations_v12(window,*,instrument,producer_source_revision,source_kind,endpoint,anchor,producer_identity,source_epoch,tick_size,units,as_of_ms,closed_through_ms,finalization_available_at_ms,ingestion_ms,already_finalized_through_ms=None):
    """Replay one declared contiguous current-v2 WS window, without IO or ACK.

    Frame UTC must be nondecreasing in this initial replay model; matched marker
    receive clocks are original frame clocks, not validation-completion clocks.
    All declarations remain unauthenticated. Ingestion is a separate explicit
    clock and contributes to conservative availability, never a commit claim.
    """
    window,anchor,tick_size,p=_capture(window,anchor,tick_size,dict(instrument=instrument,producer_source_revision=producer_source_revision,source_kind=source_kind,endpoint=endpoint,producer_identity=producer_identity,source_epoch=source_epoch,units=units,as_of_ms=as_of_ms,closed_through_ms=closed_through_ms,finalization_available_at_ms=finalization_available_at_ms,ingestion_ms=ingestion_ms,already_finalized_through_ms=already_finalized_through_ms))
    instrument=p['instrument'];revision=p['producer_source_revision'];kind=p['source_kind'];endpoint=p['endpoint']
    if type(instrument) is not dict or set(instrument)!={'exchange','category','symbol','instrument_version'} or instrument['exchange']!='bybit' or instrument['category']!='linear':raise ValueError('OBSERVATION_DECLARED_LINEAR_INSTRUMENT_REQUIRED')
    symbol=_text(instrument['symbol'],'[A-Z0-9]{2,30}')
    version=_text(instrument['instrument_version'],'[1-9][0-9]{0,18}')
    if int(version)>_U63:raise ValueError('OBSERVATION_INSTRUMENT_VERSION_REQUIRED')
    _text(revision,'[0-9a-f]{40}');_text(p['producer_identity'],'[A-Za-z0-9_.:/-]{1,128}');_text(p['source_epoch'],_UUID)
    if type(kind) is not str or kind not in _ENDPOINTS or type(endpoint) is not str or endpoint!=_ENDPOINTS[kind]:raise ValueError('OBSERVATION_CURRENT_V2_WS_SOURCE_REQUIRED_ARCHIVE_UNSUPPORTED')
    units=_units(p['units']);asof=_clock(p['as_of_ms']);closed=_clock(p['closed_through_ms']);finalization=_clock(p['finalization_available_at_ms']);ingestion=_clock(p['ingestion_ms']);finalized=p['already_finalized_through_ms']
    if closed%60000 or not closed<=finalization<=asof or ingestion>asof:raise ValueError('OBSERVATION_EXPLICIT_FINALIZATION_CLOCKS_REQUIRED')
    if finalized is not None:
        _clock(finalized)
        if finalized%60000 or finalized+60000>closed:raise ValueError('OBSERVATION_DECLARED_FINALIZED_BOUND_REQUIRED')
    decoded=[];previous=anchor.previous_metadata_sha256;last_frame_utc=None;last_frame_mono=None
    for offset,pair in enumerate(window):
        try:meta=decode_observation(pair.observation_bytes)
        except RawCaptureError as error:raise ValueError('OBSERVATION_CURRENT_V2_CANONICAL_METADATA_REQUIRED') from error
        if meta['source_kind']=='ARCHIVE' or meta['kind']=='archive_batch':raise ValueError('OBSERVATION_ARCHIVE_UNSUPPORTED')
        if meta['instrument']!=instrument or meta['producer_source_revision']!=revision or meta['source_kind']!=kind or meta['endpoint']!=endpoint or meta['connection_id']!=anchor.connection_id:raise ValueError('OBSERVATION_SOURCE_OR_INSTRUMENT_ASSOCIATION')
        index=anchor.next_observation_index+offset
        if int(meta['observation_index'])!=index or meta['previous_metadata_sha256']!=previous:raise ValueError('OBSERVATION_CONTIGUOUS_CHAIN_REQUIRED')
        payload=pair.payload_bytes;size=0 if payload is None else len(payload)
        if size!=int(meta['payload_bytes']) or (None if payload is None else _hash(payload))!=meta['payload_sha256']:raise ValueError('OBSERVATION_ACTUAL_PAYLOAD_BINDING')
        received=epoch_milliseconds_from_utc(datetime.fromisoformat(meta['received_at_utc'][:-1]+'+00:00'));_clock(received)
        if meta['kind']=='frame':
            mono=int(meta['received_monotonic_ns'])
            if last_frame_utc is not None and received<last_frame_utc:raise ValueError('OBSERVATION_INITIAL_REPLAY_FRAME_UTC_ORDER_REQUIRED')
            if last_frame_mono is not None and mono<last_frame_mono:raise ValueError('OBSERVATION_FRAME_MONOTONIC_ORDER_REQUIRED')
            last_frame_utc,last_frame_mono=received,mono
        digest=_hash(pair.observation_bytes);decoded.append(dict(pair=pair,meta=meta,index=index,sha=digest,received=received));previous=digest
    frames={row['sha']:row for row in decoded if row['meta']['kind']=='frame'};markers={key:[] for key in frames}
    # Complete raw hash/source/chain/frame association precedes trade parsing.
    for row in decoded:
        meta=row['meta'];reference=meta['frame_metadata_sha256']
        if reference is not None:
            if reference not in frames or frames[reference]['index']>=row['index']:raise ValueError('OBSERVATION_REFERENCED_FRAME_MUST_BE_IN_FULL_WINDOW')
            frame=frames[reference]
            if (meta['received_at_utc'],meta['received_monotonic_ns'])!=(frame['meta']['received_at_utc'],frame['meta']['received_monotonic_ns']):raise ValueError('OBSERVATION_MARKER_FRAME_RECEIVE_ASSOCIATION')
        if meta['kind']=='validated':
            if any(meta[key] is not None for key in ('exchange_event_at_utc','sequence','update_id')):raise ValueError('OBSERVATION_UNSUPPORTED_TRADE_VALIDATION_FIELDS')
            markers[reference].append(row)
    window_description=tuple((row['index'],row['sha'],row['meta']['payload_sha256'],row['meta']['payload_bytes']) for row in decoded)
    anchor_description=(anchor.connection_id,anchor.next_observation_index,anchor.previous_metadata_sha256)
    window_sha=_hash(_json({'schema':'market_data.raw-window-bytes.v1','anchor':anchor_description,'observations':window_description}))
    input_sha=_hash(_json({'schema':'market_data.observation-materializer.inputs.v1','window_sha256':window_sha,'parameters':p,'tick_size':str(tick_size),'availability_policy':'CONSERVATIVE_MAX3_DECLARED_NOT_COMMIT_OR_PIT','pending_policy':'FULL_WINDOW_REPLAY_ONLY_NOT_INDEPENDENT_RESUME'}))
    parsed={};deliveries={};unique=[];trade_count=0
    for digest,frame in frames.items():
        if not markers[digest]:continue
        message,_=decode_frame(frame['pair'].payload_bytes)
        trades=parse_trades(message,symbol,frame['received']);trade_count+=len(trades)
        if trade_count>8192:raise ValueError('OBSERVATION_WINDOW_EXECUTION_BUDGET')
        parsed[digest]=trades
        for trade in trades:
            _clock(trade.ts_ms);start=trade.ts_ms//60000*60000
            if finalized is not None and start<=finalized:raise ValueError('OBSERVATION_LATE_FINALIZED_EXECUTION_REFUSED')
            identity=delivery_identity(trade);key=identity['delivery_key'];content=identity['content_sha256']
            if key in deliveries:
                if deliveries[key]!=content:raise ValueError('OBSERVATION_CONFLICTING_EXECUTION_CONTENT')
                continue
            deliveries[key]=content;unique.append(dict(trade=trade,start=start,identity=identity,frame=frame,validations=tuple(markers[digest])))
    if len({item['start'] for item in unique})>1024:raise ValueError('OBSERVATION_WINDOW_MINUTE_BUDGET')
    pending_indexes=set();pending_executions=[];frame_pending={};eligible=[]
    for item in unique:
        trade=item['trade'];frame=item['frame'];reason=None
        if frame['received']>asof:reason='FUTURE_OBSERVATION'
        elif trade.ts_ms>asof:reason='FUTURE_EVENT'
        elif item['start']+60000>closed:reason='MINUTE_OPEN'
        if reason is not None:
            pending_indexes.add(frame['index']);pending_indexes.update(row['index'] for row in item['validations'])
            frame_pending.setdefault(frame['sha'],set()).add(reason)
            identity=item['identity'];pending_executions.append(PendingExecution(identity['delivery_key'],identity['content_sha256'],_json(execution_record(trade)),frame['sha'],item['validations'][0]['sha'],reason))
        else:eligible.append(item)
    discontinuities=tuple(row for row in decoded if row['received']<=asof and (row['meta']['kind'] in ('gap_observation','resync') or row['meta']['kind']=='disconnect' and row['meta']['reason']!='normal_stop'))
    quality_known=max((row['received'] for row in discontinuities),default=0)
    for item in eligible:
        if max(item['frame']['received'],item['trade'].ts_ms,quality_known)>ingestion:raise ValueError('OBSERVATION_INGESTION_PRECEDES_EMITTED_DEPENDENCY')
    states=[]
    for row in decoded:
        meta=row['meta'];which=meta['kind'];reasons=()
        if row['received']>asof:
            classification='PENDING_FUTURE_OBSERVATION';pending_indexes.add(row['index'])
        elif which=='frame':
            if not markers[row['sha']]:
                try:message,_=decode_frame(row['pair'].payload_bytes)
                except ValueError:message={}
                if message.get('op')=='subscribe' and message.get('success') is True:classification='CONTROL_SUBSCRIPTION_ACK'
                else:classification='PENDING_FRAME_AWAITING_VALIDATION';pending_indexes.add(row['index'])
            elif row['sha'] in frame_pending:classification='PENDING_FRAME_EXECUTIONS';reasons=tuple(sorted(frame_pending[row['sha']]))
            else:classification='VALIDATED_EXECUTION_FRAME' if parsed[row['sha']] else 'VALIDATED_EMPTY_EXECUTION_FRAME'
        elif which=='validated':
            frame=frames[meta['frame_metadata_sha256']]
            if frame['index'] in pending_indexes or frame['received']>asof:pending_indexes.add(row['index']);classification='PENDING_FRAME_VALIDATION'
            else:classification='MATCHED_FRAME_VALIDATION'
        else:classification='PRESERVED_CONTROL_'+which.upper()
        states.append(ObservationState(row['index'],row['sha'],which,classification,reasons))
    # Parser validation and global duplicate/conflict preflight are complete.
    # The fresh canonical builder is the sole accumulation/POC/turnover owner.
    builder=FootprintBuilder(tick_size,max_open_buckets=1024,max_trades_per_bucket=8192)
    by_minute={}
    for item in eligible:
        if builder.add(item['trade']) is not True:raise ValueError('OBSERVATION_UNEXPECTED_BUILDER_DECLINE')
        by_minute.setdefault(item['start'],[]).append(item)
    for control in discontinuities:builder.mark_open_degraded(symbol,'RAW_CAPTURE_'+control['meta']['kind'].upper()+':'+str(control['meta']['reason']))
    output=[]
    for row in sorted(builder.pop_closed(closed),key=lambda value:value['start_ms']):
        contributors=by_minute[row['start_ms']];dependency_rows={control['index']:control for control in discontinuities}
        for item in contributors:
            dependency_rows[item['frame']['index']]=item['frame']
            for validation in item['validations']:dependency_rows[validation['index']]=validation
        dependencies=tuple(MinuteObservationDependency(value['index'],value['sha'],value['meta']['kind'],value['received'],value['meta']['payload_sha256']) for _,value in sorted(dependency_rows.items()))
        received=max(value.received_at_ms for value in dependencies);known=max(received,finalization,ingestion)
        row['source_provenance']=dict(identity=p['producer_identity'],source_revision=revision,epoch=p['source_epoch'],market_type='linear',representation='live_trade_aggregate',source_kind=kind,endpoint=endpoint,instrument_version=version)
        record=minute_record_v12(row,ingestion,available_at_ms=known,units=units)
        if record['status']!='PARTIAL' or record['source_identity_verified'] is not False:raise ValueError('OBSERVATION_UNQUALIFIED_CANDIDATE_REQUIRED')
        frame_hashes=tuple(dict.fromkeys(item['frame']['sha'] for item in contributors));validation_hashes=tuple(dict.fromkeys(validation['sha'] for item in contributors for validation in item['validations']))
        output.append(MaterializedMinute(canonical(record),record['dataset_fingerprint'],frame_hashes,validation_hashes,tuple(item['identity']['delivery_key'] for item in contributors),dependencies,(('received_at_ms',received),('finalization_available_at_ms',finalization),('ingestion_ms',ingestion)),input_sha))
    if len(output)!=len(by_minute):raise ValueError('OBSERVATION_CLOSED_CANDIDATE_CONSERVATION')
    last=decoded[-1];cursor=AdvisoryObservationCursor(last['index'],last['sha'],None if last['index']==_U63 else last['index']+1,window_sha)
    pending=tuple(row['pair'] for row in decoded if row['index'] in pending_indexes);indices=tuple(row['index'] for row in decoded if row['index'] in pending_indexes)
    return MaterializedObservationWindow(input_sha,window_sha,anchor,window,tuple(states),tuple(output),pending,indices,tuple(pending_executions),cursor)
