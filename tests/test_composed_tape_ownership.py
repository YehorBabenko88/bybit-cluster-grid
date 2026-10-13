import asyncio
import json
import time
from types import SimpleNamespace
import pytest
from grid.worker import Worker
from grid.micro_tape import MicroTapeAggregator


@pytest.mark.parametrize('second_start',[1100,1250])
def test_new_trade_task_never_relabels_previous_generation_tape(monkeypatch,second_start):
    import grid.worker as module
    async def run():
        events=[];processed=asyncio.Event();frames=[]
        class Sink:
            async def insert_event(self,symbol,ts,kind,payload,ownership=None):
                events.append((kind,dict(payload),dict(ownership)))
            async def save(self,*a,**kw):pass
        class Footprint:
            def __init__(self,*a,**kw):pass
            def add(self,*a):return True
            def pop_closed(self,*a):return []
            def mark_degraded(self,*a):pass
            def mark_open_degraded(self,*a):pass
        class Socket:
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def send(self,*a):pass
            async def recv(self):
                if frames:return json.dumps(frames.pop(0))
                processed.set();await asyncio.Event().wait()
        async def online():pass
        monkeypatch.setattr(module,'FootprintBuilder',Footprint)
        monkeypatch.setattr(module,'wait_for_internet',online)
        monkeypatch.setattr(module,'websockets',SimpleNamespace(connect=lambda *a,**kw:Socket()))
        worker=Worker.__new__(Worker);worker.storage=Sink();worker.micro_storage=worker.storage
        worker.micro_tape=MicroTapeAggregator(250)
        worker.meta={'BTCUSDT':{'tick_size':.1}};worker.micro_wanted={'BTCUSDT'}
        worker.pressure=SimpleNamespace(observe_symbol=lambda *a,**kw:None)
        def trade(ts,qty):return {'topic':'publicTrade.BTCUSDT','data':[
            {'T':ts,'p':'100','v':str(qty),'S':'Buy','i':str(ts)}]}
        async def collect(generation,observations):
            worker.ownership={'BTCUSDT':{'generation':generation,'session':'session-'+str(generation),
                                         'deadline':time.monotonic()+20}}
            frames.extend([{'op':'subscribe','success':True,'args':['publicTrade.BTCUSDT']},*observations])
            processed.clear();task=asyncio.create_task(worker.trade_stream('BTCUSDT'))
            await asyncio.wait_for(processed.wait(),3)
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        await collect(1,[trade(1000,7)])
        await collect(2,[trade(second_start,2),trade(1500,3)])
        tapes=[row for kind,row,token in events if kind=='trade_tape_250ms' and token['generation']==2]
        assert len(tapes)==1
        assert tapes[0]['buy_volume']==2
        assert tapes[0]['cvd']==2
    asyncio.run(run())
