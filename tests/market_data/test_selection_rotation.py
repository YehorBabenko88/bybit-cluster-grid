"""Synthetic transport + actual canonical recorder/collector/WAL; no provider/SQL."""
import asyncio,hashlib,json,importlib.util
from decimal import Decimal
import pytest
from market_data.collector import PublicTradeCollector
from market_data.segment_wal import SegmentWAL
from market_data.raw_capture import decode_observation
from test_capture_runtime import Sink

def module():
    assert importlib.util.find_spec('market_data.selection_rotation') is not None,'canonical bounded rotation is missing'
    from market_data import selection_rotation
    return selection_rotation

class SharedSink(Sink):
    def __init__(self,path):super().__init__();self.wal=SegmentWAL(path);self.lock=asyncio.Lock();self.by_sha={}
    async def store_capture(self,**kwargs):
        async with self.lock:
            rid=await self.wal.append(dict(observation_hex=kwargs['observation_bytes'].hex(),payload_hex=None if kwargs['payload_bytes'] is None else kwargs['payload_bytes'].hex()))
            digest=hashlib.sha256(kwargs['observation_bytes']).hexdigest()
            if digest not in self.by_sha:self.by_sha[digest]=await super().store_capture(**kwargs)
            await self.wal.ack(rid);return self.by_sha[digest]

class Socket:
    def __init__(self,release,*,refuse=False):self.release=release;self.refuse=refuse;self.symbol=None;self.count=0;self.closed=False
    async def __aenter__(self):return self
    async def __aexit__(self,*args):self.closed=True
    async def send(self,value):self.symbol=json.loads(value)['args'][0].split('.',1)[1]
    async def recv(self):
        self.count+=1
        if self.count==1:return json.dumps(dict(op='subscribe',success=not self.refuse,args=['publicTrade.'+self.symbol]))
        await self.release.wait()
        return json.dumps(dict(topic='publicTrade.'+self.symbol,data=[dict(T=1999000,s=self.symbol,p='0.1',v='1e-1000',S='Buy',i='same-event')]))

def plan(symbol='BTCUSDT',tick='1E-1'):
    m=module();return m.SelectionPlan((m.SelectedInstrument(symbol,tick,1),),2678400000)

@pytest.mark.asyncio
async def test_subscription_ready_fires_only_after_actual_raw_receipt(tmp_path):
    sink=SharedSink(tmp_path/'wal');release=asyncio.Event();socket=Socket(release);seen=[]
    async def connector(endpoint):return socket
    async def ready(symbol,receipt):
        assert len(sink.rows)==1 and decode_observation(sink.rows[0][0])['kind']=='frame'
        assert receipt['frame_metadata_sha256']==hashlib.sha256(sink.rows[0][0]).hexdigest()
        seen.append((symbol,receipt))
    collector=PublicTradeCollector(sink,symbol='BTCUSDT',source_revision='a'*40,connector=connector,max_frames=1,on_subscription_ready=ready)
    await collector.run();assert len(seen)==1

@pytest.mark.asyncio
async def test_real_group_overlap_shares_wal_preserves_raw_occurrences_and_dedups_consumer(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();sockets=[];unique={};calls=[]
    async def connector(endpoint):socket=Socket(release);sockets.append(socket);return socket
    def consumer_factory(instrument):
        async def consume(trade,**binding):
            calls.append(binding['delivery_key']);unique[binding['delivery_key']]=trade
            return dict(binding,committed=True)
        return consume
    first=m.BoundedAcquisitionGroup(sink,plan(),source_revision='a'*40,execution_factory=consumer_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    second=m.BoundedAcquisitionGroup(sink,plan(),source_revision='a'*40,execution_factory=consumer_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    await first.start();await second.start();assert first.sink is second.sink is sink
    release.set();await asyncio.gather(*first.tasks,*second.tasks)
    assert len(calls)==2 and len(unique)==1 and next(iter(unique.values())).qty==Decimal('1e-1000')
    trade_raw=[raw for raw,payload in sink.rows if payload and b'same-event' in payload]
    assert len(trade_raw)==2 and trade_raw[0]!=trade_raw[1] and sink.wal.recover()==[]
    await first.stop();await second.stop();assert all(t.done() for t in first.tasks+second.tasks) and all(s.closed for s in sockets)

@pytest.mark.asyncio
async def test_failed_replacement_readiness_keeps_old_group(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();created=[]
    async def connector(endpoint):return Socket(release,refuse=len(created)>1)
    def execution_factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    def factory(selection):
        group=m.BoundedAcquisitionGroup(sink,selection,source_revision='a'*40,execution_factory=execution_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2);created.append(group);return group
    controller=m.RotationController(factory)
    await controller.rotate(plan());old=controller.current
    with pytest.raises(ValueError):await controller.rotate(plan('ETHUSDT'))
    assert controller.current is old and old.running and all(t.done() for t in created[1].tasks)
    await controller.stop();assert all(t.done() for g in created for t in g.tasks)

def test_ranked_entire_universe_filters_age_before_selecting_twenty():
    m=module();metadata=[];ranked=[]
    for i in range(25):
        symbol=f'A{i}USDT';ranked.append(symbol)
        metadata.append(dict(schema='market_data.linear-instrument.v1',symbol=symbol,tick_size='1E-1',tick_size_encoding='CANONICAL_EXACT_DECIMAL',contract_type='LinearPerpetual',status='Trading',settle_coin='USDT',launch_time='2678399999' if i<5 else '1',delivery_time=None))
    selection=m.select_from_ranked(metadata,ranked,2678400000)
    assert [i.symbol for i in selection.instruments]==ranked[5:]

@pytest.mark.asyncio
async def test_cancel_start_joins_all_owned_streams(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();sockets=[]
    class NeverAck(Socket):
        async def recv(self):await self.release.wait();return await super().recv()
    async def connector(endpoint):socket=NeverAck(release);sockets.append(socket);return socket
    def factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    group=m.BoundedAcquisitionGroup(sink,plan(),source_revision='a'*40,execution_factory=factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    starting=asyncio.create_task(group.start());await asyncio.sleep(0);await asyncio.sleep(0);starting.cancel()
    with pytest.raises(asyncio.CancelledError):await starting
    assert group.tasks and all(t.done() for t in group.tasks) and all(s.closed for s in sockets)

@pytest.mark.asyncio
async def test_unknown_replacement_sink_is_terminal_not_automatic_retry(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();calls=0
    async def connector(endpoint):return Socket(release)
    def execution_factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    class Broken:
        async def store_capture(self,**kwargs):raise RuntimeError('unknown store')
    def factory(selection):
        nonlocal calls
        calls+=1;return m.BoundedAcquisitionGroup(sink if calls==1 else Broken(),selection,source_revision='a'*40,execution_factory=execution_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    controller=m.RotationController(factory);await controller.rotate(plan());old=controller.current
    with pytest.raises(Exception):await controller.rotate(plan('ETHUSDT'))
    assert controller.failed and not old.running
    with pytest.raises(RuntimeError):await controller.rotate(plan('SOLUSDT'))
    assert calls==2

@pytest.mark.asyncio
async def test_same_symbols_with_changed_exact_tick_require_new_group(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();created=[]
    async def connector(endpoint):return Socket(release)
    def consumer_factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    def factory(selection):
        group=m.BoundedAcquisitionGroup(sink,selection,source_revision='a'*40,execution_factory=consumer_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2);created.append(group);return group
    controller=m.RotationController(factory);await controller.rotate(plan());await controller.rotate(plan(tick='10000000000000000001E-20'))
    assert len(created)==2 and all(t.done() for t in created[0].tasks)
    await controller.stop()

@pytest.mark.parametrize('clock',[True,'2678400000',-1])
def test_process_plan_clock_is_strict_integer(clock):
    m=module()
    with pytest.raises(ValueError):m.SelectionPlan((m.SelectedInstrument('BTCUSDT','1E-1',1),),clock)

@pytest.mark.asyncio
async def test_metadata_universe_cap_is_enforced_before_accumulation(monkeypatch):
    from market_data import bybit
    from types import SimpleNamespace
    async def page(*args,**kwargs):return SimpleNamespace(items=tuple(dict(symbol=f'A{i}USDT',status='Trading',contractType='LinearPerpetual',priceFilter=dict(tickSize='0.1')) for i in range(3)),next_cursor=None)
    monkeypatch.setattr(bybit,'fetch_linear_instruments_page',page)
    with pytest.raises(ValueError):await bybit.linear_symbols('https://api.bybit.com',max_attempts=1,max_instruments=2)

class HttpResponse:
    status=200;headers={}
    def __init__(self,payload):self.body=json.dumps(payload).encode();self.offset=0;self.content=self
    def raise_for_status(self):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def read(self,size):chunk=self.body[self.offset:self.offset+size];self.offset+=len(chunk);return chunk
class Session:
    def __init__(self,response):self.response=response;self.calls=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return self.response

@pytest.mark.asyncio
async def test_instrument_page_count_rejected_before_tuple_projection(monkeypatch):
    from market_data import bybit
    session=Session(HttpResponse(dict(retCode=0,result=dict(list=[{},{}]))))
    monkeypatch.setattr(bybit.aiohttp,'ClientSession',lambda **kwargs:session)
    with pytest.raises(ValueError):await bybit.fetch_linear_instruments_page('https://api.bybit.com',limit=1)

@pytest.mark.asyncio
async def test_canonical_ticker_reader_uses_existing_bounded_transport(monkeypatch):
    from market_data import bybit
    assert callable(getattr(bybit,'fetch_linear_tickers',None)),'canonical ticker ranking reader missing'
    original=dict(symbol='BTCUSDT',turnover24h='2000000',lastPrice='1.1',prevPrice24h='1',extra='ignored')
    session=Session(HttpResponse(dict(retCode=0,result=dict(list=[original]))))
    monkeypatch.setattr(bybit.aiohttp,'ClientSession',lambda **kwargs:session)
    page=await bybit.fetch_linear_tickers('https://api.bybit.com')
    assert page.rows==({'symbol':'BTCUSDT','turnover24h':'2000000','lastPrice':'1.1','prevPrice24h':'1'},)
    assert page.response.body_sha256==hashlib.sha256(session.response.body).hexdigest()
    assert session.calls[0][0]=='https://api.bybit.com/v5/market/tickers' and session.calls[0][1]['allow_redirects'] is False

@pytest.mark.asyncio
async def test_managed_revoke_after_ready_prevents_later_raw_store_and_consumer(tmp_path,monkeypatch):
    for key,value in dict(UNIFIED_MODULE_ID='market_data',UNIFIED_MODULE_VERSION='fixture',UNIFIED_RELEASE_ID='fixture',UNIFIED_INSTANCE_TOKEN='b'*64).items():monkeypatch.setenv(key,value)
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();consumed=[]
    class Admission:
        current=True
        def require_current(self):return self.current
    admission=Admission()
    async def connector(endpoint):return Socket(release)
    def factory(instrument):
        async def consume(trade,**binding):consumed.append(trade);return dict(binding,committed=True)
        return consume
    group=m.BoundedAcquisitionGroup(sink,plan(),source_revision='a'*40,execution_factory=factory,connector=connector,clock_ms=lambda:2000000,max_frames=2,startup_admission=admission)
    await group.start();admission.current=False;release.set();await asyncio.gather(*group.tasks,return_exceptions=True)
    assert consumed==[] and not any(payload and b'same-event' in payload for _,payload in sink.rows)
    await group.stop()

@pytest.mark.asyncio
async def test_cancelled_capture_remains_cancelled_when_admission_cleanup_refuses(tmp_path,monkeypatch):
    for key,value in dict(UNIFIED_MODULE_ID='market_data',UNIFIED_MODULE_VERSION='fixture',UNIFIED_RELEASE_ID='fixture',UNIFIED_INSTANCE_TOKEN='b'*64).items():monkeypatch.setenv(key,value)
    class Admission:
        current=True
        def require_current(self):return self.current
    admission=Admission();release=asyncio.Event();sink=SharedSink(tmp_path/'wal');ready=asyncio.Event()
    async def connector(endpoint):return Socket(release)
    async def subscribed(*args):ready.set()
    collector=PublicTradeCollector(sink,symbol='BTCUSDT',source_revision='a'*40,connector=connector,clock_ms=lambda:2000000,max_frames=2,on_subscription_ready=subscribed,startup_admission=admission)
    task=asyncio.create_task(collector.run());await ready.wait();admission.current=False;task.cancel()
    with pytest.raises(asyncio.CancelledError):await task

@pytest.mark.asyncio
async def test_missing_math_capability_blocks_before_any_http(monkeypatch):
    import market_math
    from market_data import bybit
    m=module();monkeypatch.delattr(market_math,'rank_volatile_symbols',raising=False)
    async def forbidden(*args,**kwargs):raise AssertionError('NO_HTTP_WITHOUT_MATH_CAPABILITY')
    monkeypatch.setattr(bybit,'linear_symbols',forbidden)
    with pytest.raises(RuntimeError,match='MATH_RANKING_CAPABILITY_REQUIRED'):await m.RankedDiscoveryPlanner(lambda:2678400000).read()

@pytest.mark.asyncio
async def test_bounded_service_lifecycle_with_declared_plans_only(tmp_path):
    # Explicit lifecycle-only input; this does NOT qualify numerical ranking.
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();groups=[]
    async def connector(endpoint):return Socket(release)
    def execution_factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    service=m.AcquisitionRotationService(sink,source_revision='a'*40,execution_factory=execution_factory,clock_ms=lambda:2000000,connector=connector,max_frames=2,max_refreshes=2,refresh_seconds=0.001)
    count=0
    async def declared():
        nonlocal count
        count+=1
        if count==2:raise ValueError('synthetic metadata unavailable')
        return plan()
    service.planner.read=declared
    original=service.controller.factory
    def observed(selection):group=original(selection);groups.append(group);return group
    service.controller.factory=observed
    result=await service.run()
    assert result['refresh_attempts']==2 and result['refresh_errors']==1 and len(groups)==1
    assert all(task.done() for group in groups for task in group.tasks)

@pytest.mark.asyncio
async def test_service_stop_cancels_and_joins_inflight_selection(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');entered=asyncio.Event()
    def execution_factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    service=m.AcquisitionRotationService(sink,source_revision='a'*40,execution_factory=execution_factory,clock_ms=lambda:2678400000,max_refreshes=2)
    async def pending():entered.set();await asyncio.Event().wait()
    service.planner.read=pending
    task=asyncio.create_task(service.run());await entered.wait();await service.stop()
    assert task.done() and task.cancelled() and service.controller._owned==set()

def metadata(symbol,launch='1',tick='1E-1'):
    return dict(schema='market_data.linear-instrument.v1',symbol=symbol,tick_size=tick,tick_size_encoding='CANONICAL_EXACT_DECIMAL',contract_type='LinearPerpetual',status='Trading',settle_coin='USDT',launch_time=launch,delivery_time=None)
def ranking_row(symbol,last,previous,turnover):return dict(symbol=symbol,lastPrice=last,prevPrice24h=previous,turnover24h=turnover)

@pytest.mark.asyncio
async def test_actual_math_ranking_retargets_original_meta_liquidity_fixture(monkeypatch):
    from market_data import bybit
    from types import SimpleNamespace
    m=module()
    async def registry(*args,**kwargs):return [metadata(s) for s in ('AAAUSDT','BBBUSDT','CCCUSDT')]
    async def tickers(*args,**kwargs):return SimpleNamespace(rows=(ranking_row('AAAUSDT','300','100','900000'),ranking_row('BBBUSDT','120','100','2000000'),ranking_row('CCCUSDT','105','100','3000000')))
    monkeypatch.setattr(bybit,'linear_symbols',registry);monkeypatch.setattr(bybit,'fetch_linear_tickers',tickers)
    result=await m.RankedDiscoveryPlanner(lambda:2678400000).read()
    assert [i.symbol for i in result.instruments]==['BBBUSDT','CCCUSDT']

@pytest.mark.asyncio
async def test_actual_math_ranks_entire_universe_before_age_and_top20(monkeypatch):
    from market_data import bybit
    from types import SimpleNamespace
    m=module();symbols=[f'A{i}USDT' for i in range(25)]
    async def registry(*args,**kwargs):return [metadata(s,'2678399999' if i<5 else '1') for i,s in enumerate(symbols)]
    async def tickers(*args,**kwargs):return SimpleNamespace(rows=tuple(ranking_row(s,'1000' if i<5 else '110','100','1000000') for i,s in enumerate(symbols)))
    monkeypatch.setattr(bybit,'linear_symbols',registry);monkeypatch.setattr(bybit,'fetch_linear_tickers',tickers)
    result=await m.RankedDiscoveryPlanner(lambda:2678400000).read()
    assert len(result.instruments)==20 and {i.symbol for i in result.instruments}==set(symbols[5:])

@pytest.mark.asyncio
async def test_actual_ranker_immutable_metadata_before_ticker_await(monkeypatch):
    from market_data import bybit
    from types import SimpleNamespace
    m=module();original=[metadata('BTCUSDT')]
    async def registry(*args,**kwargs):return original
    async def tickers(*args,**kwargs):original[0]['tick_size']='999';return SimpleNamespace(rows=(ranking_row('BTCUSDT','110','100','1000000'),))
    monkeypatch.setattr(bybit,'linear_symbols',registry);monkeypatch.setattr(bybit,'fetch_linear_tickers',tickers)
    result=await m.RankedDiscoveryPlanner(lambda:2678400000).read()
    assert result.instruments[0].tick_size=='1E-1'

@pytest.mark.asyncio
async def test_actual_ranker_hostile_context_and_declared_tie_policy(monkeypatch):
    from market_data import bybit
    from decimal import localcontext
    from types import SimpleNamespace
    m=module()
    async def registry(*args,**kwargs):return [metadata(s) for s in ('AAAUSDT','BBBUSDT','CCCUSDT')]
    async def tickers(*args,**kwargs):return SimpleNamespace(rows=(ranking_row('AAAUSDT','120','100','2000000'),ranking_row('BBBUSDT','80','100','3000000'),ranking_row('CCCUSDT','130','100','1000000')))
    monkeypatch.setattr(bybit,'linear_symbols',registry);monkeypatch.setattr(bybit,'fetch_linear_tickers',tickers)
    with localcontext() as context:
        context.prec=2;context.Emax=2;context.Emin=-2
        for signal in context.traps:context.traps[signal]=True
        context.clear_flags();result=await m.RankedDiscoveryPlanner(lambda:2678400000).read()
        assert [i.symbol for i in result.instruments]==['CCCUSDT','BBBUSDT','AAAUSDT'] and not any(context.flags.values())

@pytest.mark.asyncio
async def test_actual_service_refresh_malformed_rank_keeps_previous_group(monkeypatch,tmp_path):
    from market_data import bybit
    from types import SimpleNamespace
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();calls=0
    async def registry(*args,**kwargs):return [metadata('BTCUSDT')]
    async def tickers(*args,**kwargs):
        nonlocal calls
        calls+=1;row=ranking_row('BTCUSDT','110','100','1000000');return SimpleNamespace(rows=(row,) if calls==1 else (row,row))
    monkeypatch.setattr(bybit,'linear_symbols',registry);monkeypatch.setattr(bybit,'fetch_linear_tickers',tickers)
    async def connector(endpoint):return Socket(release)
    def factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    service=m.AcquisitionRotationService(sink,source_revision='a'*40,execution_factory=factory,clock_ms=lambda:2678400000,connector=connector,max_frames=2)
    await service.refresh_once();old=service.controller.current
    with pytest.raises(ValueError):await service.refresh_once()
    assert service.controller.current is old and old.running
    await service.stop();assert all(t.done() for t in old.tasks)

@pytest.mark.asyncio
async def test_repeated_cancel_stop_still_joins_every_owned_context(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');data=asyncio.Event();closing=asyncio.Event();release_close=asyncio.Event();sockets=[]
    class DrainingSocket(Socket):
        async def __aexit__(self,*args):
            closing.set()
            while not release_close.is_set():
                try:await release_close.wait()
                except asyncio.CancelledError:continue
            self.closed=True
    async def connector(endpoint):socket=DrainingSocket(data);sockets.append(socket);return socket
    def factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    group=m.BoundedAcquisitionGroup(sink,plan(),source_revision='a'*40,execution_factory=factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    await group.start();stopping=asyncio.create_task(group.stop());await closing.wait()
    try:
        stopping.cancel();await asyncio.sleep(0);stopping.cancel();await asyncio.sleep(0)
        assert not stopping.done()
    finally:release_close.set()
    with pytest.raises(asyncio.CancelledError):await stopping
    assert all(t.done() for t in group.tasks) and all(s.closed for s in sockets)

@pytest.mark.parametrize('body',[b'{"retCode":0,"retCode":0,"result":{"list":[]}}',b'{"retCode":false,"result":{"list":[]}}'])
def test_rest_reuses_canonical_json_rejection_of_ambiguous_control_fields(body):
    from market_data import bybit
    raw=bybit._HttpBody(200,body,hashlib.sha256(body).hexdigest(),'identity')
    with pytest.raises(ValueError):bybit._bounded_result(raw)

@pytest.mark.asyncio
async def test_failed_owned_stream_cancels_siblings_without_detached_monitor(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();never=asyncio.Event();sockets=[]
    class Selective(Socket):
        async def recv(self):
            if self.count and self.symbol=='ETHUSDT':await never.wait()
            return await super().recv()
    async def connector(endpoint):socket=Selective(release);sockets.append(socket);return socket
    def factory(instrument):
        async def consume(trade,**binding):raise RuntimeError('unknown consumer')
        return consume
    selection=m.SelectionPlan((m.SelectedInstrument('BTCUSDT','1E-1',1),m.SelectedInstrument('ETHUSDT','1E-1',1)),2678400000)
    group=m.BoundedAcquisitionGroup(sink,selection,source_revision='a'*40,execution_factory=factory,connector=connector,clock_ms=lambda:2000000,max_frames=2)
    assert hasattr(group,'failure_event'),'owned stream failure signal missing'
    await group.start();release.set()
    try:
        for _ in range(100):
            if all(t.done() for t in group.tasks):break
            await asyncio.sleep(0)
        assert group.failure_event.is_set() and all(t.done() for t in group.tasks)
        with pytest.raises(Exception):group.check()
    finally:await group.stop()
    assert all(s.closed for s in sockets)

@pytest.mark.parametrize('overrides',[{'source_revision':'bad'},{'max_frames':5},{'execution_factory':None},{'connector':None}])
def test_service_config_refuses_before_discovery_or_task_allocation(overrides):
    m=module();config=dict(source_revision='a'*40,execution_factory=lambda instrument:None,clock_ms=lambda:2678400000)
    config.update(overrides)
    with pytest.raises(ValueError):m.AcquisitionRotationService(Sink(),**config)

def test_invalid_sink_refuses_before_provider_or_task_creation():
    m=module()
    with pytest.raises(ValueError):m.AcquisitionRotationService(object(),source_revision='a'*40,execution_factory=lambda instrument:None,clock_ms=lambda:2678400000)
    with pytest.raises(ValueError):PublicTradeCollector(object(),symbol='BTCUSDT',source_revision='a'*40)

@pytest.mark.asyncio
async def test_direct_refresh_calls_share_the_same_bounded_service_budget(tmp_path):
    m=module();sink=SharedSink(tmp_path/'wal');release=asyncio.Event();reads=0
    async def connector(endpoint):return Socket(release)
    def factory(instrument):
        async def consume(trade,**binding):return dict(binding,committed=True)
        return consume
    service=m.AcquisitionRotationService(sink,source_revision='a'*40,execution_factory=factory,clock_ms=lambda:2678400000,connector=connector,max_frames=2,max_refreshes=1)
    async def declared():
        nonlocal reads
        reads+=1;return plan()
    service.planner.read=declared
    try:
        await service.refresh_once()
        with pytest.raises(RuntimeError,match='budget'):await service.refresh_once()
        assert reads==service.refresh_attempts==1
    finally:await service.stop()
