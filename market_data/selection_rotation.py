"""Bounded acquisition ownership; numerical market ranking belongs to Math."""
import asyncio
from dataclasses import dataclass
from datetime import timedelta
import re
from .collector import PublicTradeCollector,PUBLIC_ENDPOINT,public_connection
from .public_trades import _decimal,decimal_text,digest_json
from .timestamp_codec import epoch_milliseconds,utc_from_epoch_milliseconds
from .admission import startup_identity
from .raw_capture import RawCaptureError

MAX_UNIVERSE=4096

def _symbol(value):
    if type(value) is not str or re.fullmatch('[A-Z0-9]{2,30}',value) is None:raise ValueError('bounded canonical symbol required')
    return value

@dataclass(frozen=True)
class SelectedInstrument:
    symbol:str
    tick_size:str
    launch_ms:int
    def __post_init__(self):
        _symbol(self.symbol)
        if type(self.tick_size) is not str or decimal_text(_decimal(self.tick_size))!=self.tick_size:raise ValueError('canonical exact tick descriptor required')
        if type(self.launch_ms) is not int or epoch_milliseconds(self.launch_ms)<=0:raise ValueError('declared listing clock required')

@dataclass(frozen=True)
class SelectionPlan:
    instruments:tuple
    evaluated_ms:int
    def __post_init__(self):
        if type(self.instruments) is not tuple or not 1<=len(self.instruments)<=20:raise ValueError('one to twenty selected instruments required')
        if type(self.evaluated_ms) is not int:raise ValueError('strict process millisecond clock required')
        now=utc_from_epoch_milliseconds(self.evaluated_ms);seen=set()
        for item in self.instruments:
            if type(item) is not SelectedInstrument or item.symbol in seen or not item.symbol.endswith('USDT'):raise ValueError('distinct selected USDT instruments required')
            if now-utc_from_epoch_milliseconds(item.launch_ms)<timedelta(days=30):raise ValueError('thirty-day listing policy not met')
            seen.add(item.symbol)
    @property
    def key(self):return digest_json([dict(symbol=i.symbol,tick_size=i.tick_size,launch_ms=i.launch_ms) for i in self.instruments])

def _eligible_metadata(metadata,now_ms):
    if type(metadata) not in (list,tuple) or len(metadata)>MAX_UNIVERSE:raise ValueError('bounded full metadata universe required')
    if type(now_ms) is not int:raise ValueError('strict process millisecond clock required')
    now=utc_from_epoch_milliseconds(now_ms);eligible={};seen=set()
    keys={'schema','symbol','tick_size','tick_size_encoding','contract_type','status','settle_coin','launch_time','delivery_time'}
    for row in metadata:
        if type(row) is not dict or len(row)!=len(keys) or any(type(k) is not str or len(k)>64 or k not in keys for k in row):raise ValueError('closed exact instrument descriptor required')
        if row['schema']!='market_data.linear-instrument.v1' or row['tick_size_encoding']!='CANONICAL_EXACT_DECIMAL':raise ValueError('canonical instrument schema required')
        symbol=_symbol(row['symbol'])
        if symbol in seen:raise ValueError('duplicate metadata instrument')
        seen.add(symbol);item=SelectedInstrument(symbol,row['tick_size'],epoch_milliseconds(row['launch_time']))
        if symbol.endswith('USDT') and row['status']=='Trading' and now-utc_from_epoch_milliseconds(item.launch_ms)>=timedelta(days=30):eligible[symbol]=item
    return eligible

def _select_eligible(eligible,ranked,now_ms):
    if type(ranked) not in (list,tuple) or len(ranked)>MAX_UNIVERSE:raise ValueError('bounded full ranking required')
    selected=[];seen=set()
    for symbol in ranked:
        _symbol(symbol)
        if symbol in seen:raise ValueError('duplicate ranked instrument')
        seen.add(symbol)
        if symbol in eligible:selected.append(eligible[symbol])
    return SelectionPlan(tuple(selected[:20]),epoch_milliseconds(now_ms))

def select_from_ranked(metadata,ranked,now_ms):
    return _select_eligible(_eligible_metadata(metadata,now_ms),ranked,now_ms)

async def _join(tasks):
    if not tasks:return
    future=asyncio.gather(*tasks,return_exceptions=True);cancelled=False
    while not future.done():
        try:await asyncio.shield(future)
        except asyncio.CancelledError:cancelled=True
    future.result()
    if cancelled:raise asyncio.CancelledError


def _acquisition_config(sink,source_revision,execution_factory,connector,clock_ms,max_frames,start_timeout=20):
    if not callable(getattr(sink,'store_capture',None)) or not callable(execution_factory) or not callable(connector) or not callable(clock_ms) or type(max_frames) is not int or not 1<=max_frames<=4 or type(start_timeout) not in (int,float) or not 0<start_timeout<=20 or type(source_revision) is not str or re.fullmatch('[0-9a-f]{40}',source_revision) is None:raise ValueError('bounded acquisition configuration required')

class BoundedAcquisitionGroup:
    def __init__(self,sink,selection,*,source_revision,execution_factory,connector=public_connection,clock_ms,max_frames=4,start_timeout=20,startup_admission=None):
        _acquisition_config(sink,source_revision,execution_factory,connector,clock_ms,max_frames,start_timeout)
        if type(selection) is not SelectionPlan:raise ValueError('immutable selection plan required')
        self.sink=sink;self.selection=selection;self.revision=source_revision;self.execution_factory=execution_factory;self.connector=connector;self.clock_ms=clock_ms;self.max_frames=max_frames;self.start_timeout=start_timeout;self.startup_admission=startup_admission
        self.tasks=();self.collectors=[];self._waiter=None;self._started=False;self._stopped=False;self._identity=None;self.failure_event=asyncio.Event();self._error=None
    def _current(self):
        if startup_identity(self.startup_admission)!=self._identity:raise RuntimeError('group admission changed')
    @property
    def running(self):return not self._stopped and any(not t.done() for t in self.tasks)
    def _task_done(self,task):
        try:self.check()
        except BaseException as error:
            if self._error is None:self._error=error
            self.failure_event.set()
            for sibling in self.tasks:
                if sibling is not task and not sibling.done():sibling.cancel()
    def check(self):
        # A cancelled task may have committed before losing its ACK. Inspect
        # completed collectors BEFORE ordinary task errors can mask uncertainty.
        for collector,task in zip(self.collectors,self.tasks):
            if task.done():collector.require_known_outcome()
        if self._error is not None:raise self._error
        for task in self.tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:raise task.exception()
    async def start(self):
        if self._started or self._stopped:raise RuntimeError('acquisition group is one-shot')
        self._started=True;self._identity=startup_identity(self.startup_admission);events=[];owned=[]
        try:
            for instrument in self.selection.instruments:
                event=asyncio.Event();events.append(event)
                async def ready(symbol,receipt,expected=instrument.symbol,event=event):
                    self._current()
                    required=dict(schema='market_data.subscription-ready.v1',symbol=expected,endpoint=PUBLIC_ENDPOINT,producer_source_revision=self.revision,readiness_scope='SUBSCRIPTION_ACK_CAPTURED_NOT_MARKET_COVERAGE',source_authenticity='UNKNOWN',coverage='UNKNOWN')
                    if symbol!=expected or type(receipt) is not dict or len(receipt)!=8 or any(receipt.get(k)!=v for k,v in required.items()) or type(receipt.get('frame_metadata_sha256')) is not str or re.fullmatch('[a-f0-9]{64}',receipt['frame_metadata_sha256']) is None:raise ValueError('exact raw subscription readiness required')
                    event.set()
                callback=self.execution_factory(instrument)
                if not callable(callback):raise ValueError("exact execution receipt consumer required")
                collector=PublicTradeCollector(self.sink,symbol=instrument.symbol,source_revision=self.revision,connector=self.connector,clock_ms=self.clock_ms,max_frames=self.max_frames,on_execution=callback,on_subscription_ready=ready,startup_admission=self.startup_admission)
                self.collectors.append(collector);task=asyncio.create_task(collector.run());owned.append(task);self.tasks=tuple(owned);task.add_done_callback(self._task_done)
            async def all_ready():await asyncio.gather(*(event.wait() for event in events))
            self._waiter=asyncio.create_task(all_ready());watched=set(self.tasks)|{self._waiter}
            async with asyncio.timeout(self.start_timeout):
                while not self._waiter.done():
                    self._current();done,_=await asyncio.wait(watched,return_when=asyncio.FIRST_COMPLETED)
                    self.check()
                    for task in done:
                        if task is not self._waiter:
                            watched.discard(task)
                            if task.cancelled():raise RuntimeError('acquisition ended before readiness')
                            error=task.exception()
                            if error is not None:raise error
                await self._waiter
            self._current();self.check()
            return dict(status='SUBSCRIPTION_ACKS_CAPTURED',source_authenticity='UNKNOWN',coverage='UNKNOWN')
        except BaseException:
            await self.stop();raise
    async def stop(self):
        self._stopped=True;owned=list(self.tasks)+([self._waiter] if self._waiter is not None else [])
        for task in owned:
            if not task.done():task.cancel()
        await _join(owned)

class RotationController:
    def __init__(self,group_factory):
        if not callable(group_factory):raise ValueError('group factory required')
        self.factory=group_factory;self.current=None;self._owned=set();self._lock=asyncio.Lock();self.failed=False
    async def _stop_owned(self):
        groups=tuple(self._owned)
        stops=tuple(asyncio.create_task(group.stop()) for group in groups)
        try:await _join(stops)
        finally:self._owned={g for g in groups if any(not t.done() for t in g.tasks)}
    async def rotate(self,selection):
        if type(selection) is not SelectionPlan:raise ValueError('immutable selection plan required')
        async with self._lock:
            if self.failed:raise RuntimeError('rotation owner failed')
            if self.current is not None:
                try:self.current.check()
                except BaseException:
                    self.failed=True;await self._stop_owned();raise
                if self.current.selection.key==selection.key and self.current.running:return dict(status='UNCHANGED',source_authenticity='UNKNOWN')
            previous=self.current;replacement=self.factory(selection);self._owned.add(replacement)
            try:
                await replacement.start()
            except asyncio.CancelledError:
                self.failed=True;await self._stop_owned();raise
            except Exception as error:
                try:
                    await replacement.stop()
                    # Failure of the new start must never hide terminal failure
                    # in the old group while the start/cleanup awaited.
                    if previous is not None:previous.check()
                    try:replacement.check()
                    except RawCaptureError:raise
                    except Exception:pass  # Known rejected start; original error follows.
                except BaseException:
                    self.failed=True;await self._stop_owned();raise
                if isinstance(error,(RawCaptureError,TimeoutError)):
                    self.failed=True;await self._stop_owned()
                else:self._owned.discard(replacement)
                raise
            try:
                # Readiness can await long enough for old ownership to become
                # uncertain. Drain can itself lose an ACK: check BOTH boundaries.
                if previous is not None:
                    previous.check()
                    await previous.stop()
                    previous.check()
                replacement.check()
            except BaseException:
                self.failed=True;await self._stop_owned();raise
            # No await separates the final checks from accepting new ownership.
            self.current=replacement
            if previous is not None:self._owned.discard(previous)
            return dict(status='ROTATED',selection_key=selection.key,source_authenticity='UNKNOWN',coverage='UNKNOWN')
    async def stop(self):
        async with self._lock:await self._stop_owned()


class RankedDiscoveryPlanner:
    def __init__(self,clock_ms,*,base_url='https://api.bybit.com',startup_admission=None):
        if not callable(clock_ms) or base_url!='https://api.bybit.com':raise ValueError('explicit clock and canonical public origin required')
        self.clock_ms=clock_ms;self.base_url=base_url;self.startup_admission=startup_admission
    async def read(self):
        try:from market_math import rank_volatile_symbols
        except ImportError:raise RuntimeError('MATH_RANKING_CAPABILITY_REQUIRED') from None
        from .bybit import linear_symbols,fetch_linear_tickers
        identity=startup_identity(self.startup_admission)
        def current():
            if startup_identity(self.startup_admission)!=identity:raise RawCaptureError('SELECTION_ADMISSION_CHANGED')
        current();metadata=await linear_symbols(self.base_url,max_instruments=MAX_UNIVERSE);current()
        now=self.clock_ms();eligible=_eligible_metadata(metadata,now)
        # Detach ALL metadata before the next I/O await; values are frozen
        # instrument descriptors, never retained references to input dictionaries.
        page=await fetch_linear_tickers(self.base_url,max_rows=MAX_UNIVERSE);current()
        ranked=rank_volatile_symbols(page.rows)
        return _select_eligible(eligible,ranked,now)

class AcquisitionRotationService:
    def __init__(self,sink,*,source_revision,execution_factory,clock_ms,connector=public_connection,max_frames=4,max_refreshes=4,refresh_seconds=300,startup_admission=None):
        if type(max_refreshes) is not int or not 1<=max_refreshes<=8 or type(refresh_seconds) not in (int,float) or not 0<refresh_seconds<=300:raise ValueError('bounded refresh lifecycle required')
        _acquisition_config(sink,source_revision,execution_factory,connector,clock_ms,max_frames)
        self.sink=sink;self.source_revision=source_revision;self.execution_factory=execution_factory;self.clock_ms=clock_ms;self.connector=connector;self.max_frames=max_frames;self.max_refreshes=max_refreshes;self.refresh_seconds=refresh_seconds;self.startup_admission=startup_admission
        self.planner=RankedDiscoveryPlanner(clock_ms,startup_admission=startup_admission)
        self.controller=RotationController(lambda selection:BoundedAcquisitionGroup(self.sink,selection,source_revision=self.source_revision,execution_factory=self.execution_factory,connector=self.connector,clock_ms=self.clock_ms,max_frames=self.max_frames,startup_admission=self.startup_admission))
        self.stop_event=asyncio.Event();self.refresh_errors=0;self.refresh_attempts=0;self._started=False;self._closed=False;self._run_task=None;self._refresh_owner=None;self._refresh_lock=asyncio.Lock();self._identity=None;self._admitted=False;self._waiters=()
    def _current(self):
        try:identity=startup_identity(self.startup_admission)
        except Exception:raise RawCaptureError('CURRENT_SELECTION_ADMISSION_REQUIRED') from None
        if not self._admitted:self._identity=identity;self._admitted=True
        elif identity!=self._identity:raise RawCaptureError('SELECTION_MANAGED_IDENTITY_CHANGED')
    async def refresh_once(self):
        async with self._refresh_lock:
            if self._closed:raise RuntimeError('rotation service closed')
            if self.refresh_attempts>=self.max_refreshes:raise RuntimeError('selection refresh budget exhausted')
            self._refresh_owner=asyncio.current_task();self.refresh_attempts+=1
            try:
                self._current();selection=await self.planner.read();self._current()
                return await self.controller.rotate(selection)
            except RawCaptureError:
                self.controller.failed=True;await self.controller.stop();raise
            finally:self._refresh_owner=None
    async def _wait_refresh(self):
        if self.controller.current is not None:self.controller.current.check()
        waiters=[asyncio.create_task(self.stop_event.wait())]
        if self.controller.current is not None:waiters.append(asyncio.create_task(self.controller.current.failure_event.wait()))
        self._waiters=tuple(waiters)
        try:
            await asyncio.wait(self._waiters,timeout=self.refresh_seconds,return_when=asyncio.FIRST_COMPLETED)
            if self.controller.current is not None:self.controller.current.check()
        finally:
            for task in waiters:
                if not task.done():task.cancel()
            try:await _join(tuple(waiters))
            finally:self._waiters=()
    async def run(self):
        if self._started or self._closed:raise RuntimeError('rotation service is one-shot')
        self._started=True;self._run_task=asyncio.current_task()
        try:
            for cycle in range(self.max_refreshes):
                if self.stop_event.is_set() or self.refresh_attempts>=self.max_refreshes:break
                try:await self.refresh_once()
                except asyncio.CancelledError:raise
                except Exception:
                    if self.controller.failed:raise
                    self.refresh_errors+=1
                if cycle+1<self.max_refreshes and not self.stop_event.is_set():
                    await self._wait_refresh()
        finally:
            self._closed=True
            try:await self.controller.stop()
            finally:self._run_task=None
        if self.controller.current is not None:self.controller.current.check()
        self._current()
        return dict(schema='market_data.rotation.receipt.v1',collection_mode='BOUNDED_CAPTURE_EPOCHS_NOT_CONTINUOUS',refresh_attempts=self.refresh_attempts,refresh_errors=self.refresh_errors,source_authenticity='UNKNOWN',coverage='UNKNOWN',point_in_time_availability='UNKNOWN',execution_authority=False,trading_authorized=False)
    async def stop(self):
        self._closed=True;self.stop_event.set();current=asyncio.current_task()
        owners={task for task in (self._run_task,self._refresh_owner) if task is not None and task is not current and not task.done()}
        for task in owners:task.cancel()
        try:await _join(tuple(owners))
        finally:await self.controller.stop()
