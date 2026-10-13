"""No exchange: kill an actual collector process while its buckets are open."""
import os
import subprocess
import sys
import time

from grid.segment_wal import SegmentWAL


COLLECTOR = r'''
import asyncio,json,time,sys,pathlib
from types import SimpleNamespace
import grid.worker as module
from grid.worker import Worker
from grid.segment_wal import SegmentWAL
from grid.micro_tape import MicroTapeAggregator

root=pathlib.Path(sys.argv[1]);mode=sys.argv[2]
class Sink:
    def __init__(self):self.wal=SegmentWAL(root/'wal')
    async def save(self,*args,**kwargs):raise AssertionError('minute still open')
    async def insert_event(self,symbol,ts,kind,payload,ownership=None):
        await self.wal.append({'symbol':symbol,'event_ts':ts,'event_type':kind,
                               'payload':payload,'ownership':ownership})
        if mode=='admission':
            (root/'ready').write_text('durable-before-admission')
            await asyncio.Event().wait()
class Tape(MicroTapeAggregator):
    def add(self,trade):
        row=super().add(trade)
        (root/'ready').write_text('aggregated')
        return row
class Socket:
    def __init__(self):self.counter=0
    async def send(self,*args):pass
    async def recv(self):
        self.counter+=1
        if self.counter==1:return json.dumps({'op':'subscribe','success':True,'args':
            ['orderbook.50.BTCUSDT','tickers.BTCUSDT'] if mode=='book' else ['publicTrade.BTCUSDT']})
        if self.counter==2 and mode=='book':return json.dumps({'topic':'orderbook.50.BTCUSDT',
            'type':'snapshot','ts':int(time.time()*1000),
            'data':{'b':[['99','2']],'a':[['101','3']],'u':1,'seq':1}})
        if self.counter==2:return json.dumps({'topic':'publicTrade.BTCUSDT','ts':1700000000123,
            'data':[{'T':1700000000123,'p':'100','v':'2','S':'Buy','i':'unique-trade'}]})
        if mode=='book':(root/'ready').write_text('book-processed')
        await asyncio.Event().wait()
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
async def online():pass
module.wait_for_internet=online
module.websockets=SimpleNamespace(connect=lambda *a,**kw:Socket())
w=Worker.__new__(Worker);w.storage=Sink();w.micro_storage=w.storage
w.ownership={'BTCUSDT':{'generation':7,'session':'original-session','deadline':time.monotonic()+120}}
w.meta={'BTCUSDT':{'tick_size':.1}};w.micro_wanted={'BTCUSDT'}
w.micro_tape=Tape(250);w.pressure=SimpleNamespace(observe_symbol=lambda *a,**kw:None)
if mode=='book':
    import grid.microstructure as micro
    import os
    if os.environ.get('GRID_AUDIT_OLD_MICRO'):
        exec(compile(pathlib.Path(os.environ['GRID_AUDIT_OLD_MICRO']).read_text(encoding='utf-8-sig'),
                     'old_microstructure','exec'),micro.__dict__)
    micro.wait_for_internet=online
    micro.websockets=SimpleNamespace(connect=lambda *a,**kw:Socket())
    from grid.collection_ownership import OwnedSink
    asyncio.run(micro.MicrostructureCollector(OwnedSink(w.micro_storage,w.ownership,w.ownership),
                                             snapshot_ms=1000).run_batch(['BTCUSDT']))
else:
    asyncio.run(w.trade_stream('BTCUSDT'))
'''


def capture_after_kill(tmp_path,mode):
    env=dict(os.environ,GRID_SHARED_TOKEN='test-token')
    child=subprocess.Popen([sys.executable,'-c',COLLECTOR,str(tmp_path),mode],env=env,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+12
        while not (tmp_path/'ready').exists():
            if child.poll() is not None:
                raise AssertionError(child.communicate()[1].decode())
            assert time.monotonic()<deadline,'collector failed to reach crash barrier'
            time.sleep(.02)
        child.kill();child.communicate(timeout=5)
        wal=SegmentWAL(tmp_path/'wal')
        try:return wal.recover()
        finally:wal.close()
    finally:
        if child.poll() is None:child.kill();child.communicate(timeout=5)


def test_open_minute_and_micro_bucket_keep_durable_source_after_process_kill(tmp_path):
    records=capture_after_kill(tmp_path,'aggregate')
    assert len(records)==1
    _,row=records[0]
    assert row['event_type']=='public_trade_capture_evidence'
    assert row['ownership']=={'generation':7,'session':'original-session'}
    assert row['payload']['messages'][0]['trades'][0]['i']=='unique-trade'


def test_kill_after_wal_before_queue_admission_preserves_unaggregated_source(tmp_path):
    records=capture_after_kill(tmp_path,'admission')
    assert len(records)==1
    assert records[0][1]['payload']['capture_stage']=='PRE_AGGREGATION'


def test_book_source_survives_process_kill_with_original_sequence(tmp_path):
    records=capture_after_kill(tmp_path,'book')
    evidence=[row for _,row in records if row['event_type']=='orderbook_capture_evidence']
    assert len(evidence)==1
    assert evidence[0]['payload']['events'][0]['seq']==1
    assert evidence[0]['ownership']=={'generation':7,'session':'original-session'}
