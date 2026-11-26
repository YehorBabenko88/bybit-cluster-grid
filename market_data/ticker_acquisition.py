"""Bounded ticker lifecycle; original raw WAL recovery, no normalized SQL writer."""
import asyncio
import copy
import json
import re
import uuid
from market_math import paper_input_numeric_integrity
from .admission import startup_identity
from .collector import PUBLIC_ENDPOINT,public_connection
from .public_trades import decode_frame,digest_json,MAX_FRAME_BYTES
from .raw_capture import RawCaptureRecorder,RawCaptureProfile,RawCaptureError,decode_observation,validate_capture_receipt

FIELD_MAP=dict(openInterest='open_interest',openInterestValue='open_interest_value',fundingRate='funding_rate',fundingIntervalHour='funding_interval_hour',nextFundingTime='next_funding_time',markPrice='mark_price',indexPrice='index_price',lastPrice='last_price',basisRate='basis_rate',bid1Price='bid1_price',bid1Size='bid1_size',ask1Price='ask1_price',ask1Size='ask1_size',volume24h='volume24h',turnover24h='turnover24h')
FUNDING=frozenset(('funding_rate','funding_interval_hour','next_funding_time'))

def _symbol(value):
    if type(value) is not str or re.fullmatch('[A-Z0-9]{2,30}',value) is None:raise ValueError('invalid ticker instrument')
    return value

def _clock(value):
    if type(value) is not int or not 0<value<=253402300799999:raise ValueError('strict provider/process millisecond clock required')
    return value

def _scalar(value):
    if value is None or value=='':return None
    if type(value) is str and len(value)<=128:return value
    if type(value) is int and len(str(value))<=128:return value
    # Provider numbers must preserve original JSON value hash; binary64 numeric
    # tokens are bounded by decoder and validated only by Math for funding.
    if type(value) is float:
        json.dumps(value,allow_nan=False);return value
    raise ValueError('bounded original scalar required')

class TickerState:
    def __init__(self,symbol):self.symbol=_symbol(symbol);self._epoch=None;self._values={};self._proofs={};self._last=0;self._fresh=False
    def begin_epoch(self,connection_id):
        if type(connection_id) is not str or re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',connection_id) is None:raise ValueError('explicit connection epoch required')
        self._epoch=connection_id;self._values={};self._proofs={};self._last=0;self._fresh=False
    def invalidate(self):self._fresh=False
    def snapshot(self):
        return dict(schema='market_data.ticker-state.v1',symbol=self.symbol,connection_id=self._epoch,values=copy.deepcopy(self._values),field_observations=dict(schema='market_data.ticker-field-observations.v1',clock_basis='EXCHANGE_FRAME_TS_AND_PROCESS_WALL_CLOCK',fields=copy.deepcopy(self._proofs)),event_ms=self._last,fresh_snapshot=self._fresh,nonfunding_numeric_status='UNVALIDATED',source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN')
    def prepare(self,message,observed_ms):
        _clock(observed_ms)
        if self._epoch is None or type(message) is not dict or message.get('topic')!='tickers.'+self.symbol or message.get('type') not in ('snapshot','delta'):raise ValueError('ticker envelope required')
        event=_clock(message.get('ts'));data=message.get('data')
        if event>observed_ms or event<self._last or type(data) is not dict or len(data)>64:raise ValueError('ticker clock/data refused')
        updates={FIELD_MAP[k]:_scalar(v) for k,v in data.items() if k in FIELD_MAP}
        if not updates:raise ValueError('empty or unknown-only ticker delta')
        funding={k:v for k,v in updates.items() if k in FUNDING}
        if funding and not paper_input_numeric_integrity('derivatives_ticker',funding):raise ValueError('ticker funding numeric integrity refused')
        candidate=self.snapshot();candidate['event_ms']=event;candidate['fresh_snapshot']=self._fresh or message['type']=='snapshot'
        for name,value in updates.items():
            candidate['values'][name]=value
            if name in FUNDING:
                previous=candidate['field_observations']['fields'].pop(name,None)
                if value is not None and (previous is None or event>=previous['event_ms'] and observed_ms>=previous['observed_ms']):
                    candidate['field_observations']['fields'][name]=dict(event_ms=event,observed_ms=observed_ms,value_sha256=digest_json(value))
        return candidate
    def commit(self,candidate):
        if candidate['connection_id']!=self._epoch:raise ValueError('ticker candidate epoch mismatch')
        self._values=copy.deepcopy(candidate['values']);self._proofs=copy.deepcopy(candidate['field_observations']['fields']);self._last=candidate['event_ms'];self._fresh=candidate['fresh_snapshot']

class _JournalSink:
    def __init__(self,sink,wal,admit):self.sink=sink;self.wal=wal;self.admit=admit
    async def store_capture(self,*,observation_bytes,payload_bytes):
        self.admit()
        await self.wal.append(dict(schema='market_data.ticker-wal.v1',kind='raw',observation_hex=observation_bytes.hex(),payload_hex=None if payload_bytes is None else payload_bytes.hex()))
        self.admit()
        return await self.sink.store_capture(observation_bytes=observation_bytes,payload_bytes=payload_bytes)

class TickerAcquisition:
    def __init__(self,sink,wal,*,symbol,source_revision,on_ticker,connector=public_connection,clock_ms=None,max_frames=4,endpoint=PUBLIC_ENDPOINT,startup_admission=None):
        if type(endpoint) is not str or endpoint!=PUBLIC_ENDPOINT or type(source_revision) is not str or re.fullmatch('[0-9a-f]{40}',source_revision) is None or type(max_frames) is not int or not 1<=max_frames<=4 or not callable(on_ticker) or not callable(connector) or (clock_ms is not None and not callable(clock_ms)):raise ValueError('bounded ticker acquisition configuration required')
        self.symbol=_symbol(symbol);self.source_revision=source_revision;self.endpoint=endpoint;self.sink=sink;self.wal=wal;self.consumer=on_ticker;self.connector=connector;self.clock_ms=clock_ms;self.max_frames=max_frames;self.failed=False;self._started=False;self.state=TickerState(symbol);self.recorder=None;self.startup_admission=startup_admission;self._identity=None
    def _current(self):
        if startup_identity(self.startup_admission)!=self._identity:raise RuntimeError('ticker managed identity changed')
    def _pending(self):
        rows=[]
        for rid,payload in self.wal.iter_recover():
            if len(rows)>=16:raise ValueError('ticker recovery record budget exceeded')
            if type(payload) is not dict or payload.get('schema')!='market_data.ticker-wal.v1':raise ValueError('exclusive ticker WAL required')
            rows.append((rid,payload))
        return rows
    def recovery_pending(self):
        return [dict(source_revision=self.source_revision,recovery_mode='RECONCILIATION_REQUIRED',point_in_time_availability='UNKNOWN',record_id=rid,record=copy.deepcopy(payload)) for rid,payload in self._pending()]
    def _receipt(self,receipt,binding):
        if type(receipt) is not dict or set(receipt)!=set(binding)|{'committed'} or receipt.get('committed') is not True or any(type(receipt[k]) is not str or receipt[k]!=v for k,v in binding.items()):raise RawCaptureError('TICKER_CONSUMER_OUTCOME_UNKNOWN')
    async def _ack(self):
        self._current()
        ids=[rid for rid,_ in self._pending()]
        if ids:await self.wal.ack_prefix(ids)
    async def _deliver(self,payload,binding,mode):
        self._current()
        binding=dict(binding,recovery_mode=mode)
        receipt=await asyncio.wait_for(self.consumer(copy.deepcopy(payload),**binding),timeout=20)
        self._current()
        self._receipt(receipt,binding)
    async def recover(self):
        if self._started or self.failed:raise RawCaptureError('TICKER_OWNER_REUSE_REFUSED')
        self._started=True
        try:
            self._identity=startup_identity(self.startup_admission)
            pending=self._pending()
            # Validate ALL original bytes/bindings before any side effect.
            decoded=[];frames={};previous=None;total_bytes=0
            for rid,item in pending:
                if item.get('kind')=='raw':
                    if set(item)!={'schema','kind','observation_hex','payload_hex'} or type(item['observation_hex']) is not str or len(item['observation_hex'])>32768 or (item['payload_hex'] is not None and (type(item['payload_hex']) is not str or len(item['payload_hex'])>2*MAX_FRAME_BYTES)):raise ValueError('bounded original raw WAL required')
                    raw=bytes.fromhex(item['observation_hex']);payload=None if item['payload_hex'] is None else bytes.fromhex(item['payload_hex']);obs=decode_observation(raw)
                    if obs['producer_source_revision']!=self.source_revision or obs['instrument']['symbol']!=self.symbol or obs['endpoint']!=self.endpoint:raise ValueError('ticker recovery source mismatch')
                    total_bytes+=len(raw)+len(payload or b'')
                    if total_bytes>4194304+16*16384:raise ValueError('ticker recovery aggregate byte budget exceeded')
                    raw_sha=digest_json(obs)
                    if previous is not None and (obs['connection_id']!=previous['connection_id'] or int(obs['observation_index'])!=int(previous['observation_index'])+1 or obs['previous_metadata_sha256']!=digest_json(previous)):raise ValueError('ticker raw chain drift')
                    if obs['kind']=='frame':frames[raw_sha]=(obs,payload)
                    previous=obs
                    decoded.append((rid,'raw',raw,payload))
                elif item.get('kind')=='delivery':
                    if set(item)!={'schema','kind','payload','binding'} or type(item['payload']) is not dict or type(item['binding']) is not dict:raise ValueError('ticker delivery WAL refused')
                    b=item['binding'];p=item['payload']
                    if set(b)!={'source_revision','endpoint','connection_id','frame_metadata_sha256','delivery_sha256'} or b['source_revision']!=self.source_revision or b['endpoint']!=self.endpoint or b['connection_id']!=p.get('connection_id') or b['delivery_sha256']!=digest_json(p):raise ValueError('ticker delivery binding drift')
                    if b['frame_metadata_sha256'] not in frames or p.get('frame_metadata_sha256')!=b['frame_metadata_sha256'] or p.get('producer_source_revision')!=self.source_revision or p.get('endpoint')!=self.endpoint or p.get('symbol')!=self.symbol or 'fresh_snapshot' in p:raise ValueError('ticker delivery has no original frame binding')
                    obs,raw_payload=frames[b['frame_metadata_sha256']]
                    if obs['connection_id']!=b['connection_id']:raise ValueError('ticker delivery epoch drift')
                    original,_=decode_frame(raw_payload)
                    if original.get('topic')!='tickers.'+self.symbol or original.get('ts')!=p.get('event_ms'):raise ValueError('ticker delivery event drift')
                    decoded.append((rid,'delivery',p,b))
                else:raise ValueError('ticker WAL kind refused')
            for rid,kind,first,second in decoded:
                if kind=='raw':
                    self._current()
                    facts=await asyncio.wait_for(self.sink.store_capture(observation_bytes=first,payload_bytes=second),20);validate_capture_receipt(facts,first,second)
                else:await self._deliver(first,second,'RECOVERY_UNKNOWN_NOT_FRESH')
            await self._ack()
        except BaseException:self.failed=True;raise
        return dict(recovered_records=len(pending),fresh_snapshot=False,source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN')
    async def run(self):
        if self._started or self.failed:raise RawCaptureError('TICKER_OWNER_REUSE_REFUSED')
        self._started=True
        if self.clock_ms is None:self.failed=True;raise ValueError('explicit process millisecond clock provider required')
        if self._pending():self.failed=True;raise RawCaptureError('TICKER_RECOVERY_REQUIRED')
        self._identity=startup_identity(self.startup_admission)
        cid=str(uuid.uuid4());self.state.begin_epoch(cid)
        self.recorder=RawCaptureRecorder(_JournalSink(self.sink,self.wal,self._current),instrument=dict(exchange='bybit',category='linear',symbol=self.symbol,instrument_version='1'),producer_source_revision=self.source_revision,source_kind='PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED',endpoint=self.endpoint,profile=RawCaptureProfile(16,4194304,MAX_FRAME_BYTES,16384,2),connection_id_factory=lambda:cid)
        self.recorder.begin_connection();subscribed=False;accepted=0
        try:
            connection=await self.connector(self.endpoint)
            async with connection as ws:
                self._current()
                await ws.send(json.dumps(dict(op='subscribe',args=['tickers.'+self.symbol])))
                for _ in range(self.max_frames):
                    self._current()
                    raw=await asyncio.wait_for(ws.recv(),30)
                    self._current()
                    reference=await asyncio.wait_for(self.recorder.frame(raw),20)
                    try:
                        message,_=decode_frame(raw)
                        if message.get('op')=='subscribe':
                            args=message.get('args',message.get('data',{}).get('args') if type(message.get('data')) is dict else None)
                            if subscribed or message.get('success') is not True or type(args) is not list or args!=['tickers.'+self.symbol]:raise ValueError('ticker subscription ACK refused')
                            subscribed=True;await self._ack();continue
                        if not subscribed:raise ValueError('ticker before subscription ACK')
                        candidate=self.state.prepare(message,self.clock_ms())
                    except ValueError:
                        await asyncio.wait_for(self.recorder.gap('frame_invalid',reference),20);await self._ack();raise
                    await asyncio.wait_for(self.recorder.validated(reference,exchange_event_ms=candidate['event_ms']),20)
                    publication=copy.deepcopy(candidate)
                    publication['original_epoch_snapshot_seen']=publication.pop('fresh_snapshot')
                    publication['frame_metadata_sha256']=reference.metadata_sha256
                    publication['producer_source_revision']=self.source_revision
                    publication['endpoint']=self.endpoint
                    binding=dict(source_revision=self.source_revision,endpoint=self.endpoint,connection_id=cid,frame_metadata_sha256=reference.metadata_sha256,delivery_sha256=digest_json(publication))
                    await self.wal.append(dict(schema='market_data.ticker-wal.v1',kind='delivery',payload=copy.deepcopy(publication),binding=binding))
                    await self._deliver(publication,binding,'ORIGINAL_EPOCH_UNATTESTED')
                    await self._ack();self.state.commit(candidate);accepted+=1
                await asyncio.wait_for(self.recorder.disconnect('normal_stop'),20);await self._ack()
        except BaseException as error:
            self.failed=True;self.state.invalidate()
            try:
                if not self._pending() and not self.recorder.metrics()['failed']:
                    self._current()
                    await asyncio.wait_for(self.recorder.disconnect('cancelled' if isinstance(error,asyncio.CancelledError) else 'transport_error'),20)
                    await self._ack()
            except BaseException:
                pass  # Original cancellation/failure wins; new uncertain WAL stays pending.
            # Preserve the original exception, pending exact raw/delivery bytes,
            # and prior committed state. Never retry/reconnect uncertain effects.
            raise
        return dict(schema='market_data.ticker-capture.receipt.v1',accepted_observations=accepted,source_authenticity='UNKNOWN',coverage='UNKNOWN',point_in_time_availability='UNKNOWN',execution_authority=False,trading_authorized=False)
