import asyncio
from types import SimpleNamespace
import pytest
from grid.micro_event_storage import MicroEventStorage
from grid.storage import Storage
from grid.segment_wal import SegmentWAL


@pytest.mark.parametrize('kind',['event','minute'])
def test_admitted_payload_cannot_drift_from_wal_before_delivery(tmp_path,kind):
    async def run():
        wal=SegmentWAL(tmp_path/'wal');admitted=[]
        async def put(rid,row):admitted.append(row)
        sink=(MicroEventStorage if kind=='event' else Storage).__new__(MicroEventStorage if kind=='event' else Storage)
        sink.spool=wal;sink.replay_done=asyncio.Event();sink.replay_done.set()
        sink._enqueue_lock=asyncio.Lock();sink.write_queue=SimpleNamespace(put=put)
        payload={'trades':[{'qty':1}]}
        try:
            if kind=='event':
                await sink.insert_event('BTCUSDT',1,'public_trade_capture_evidence',payload)
            else:
                await sink.save({'symbol':'BTCUSDT','start_ms':1,'levels':payload['trades']})
            payload['trades'][0]['qty']=99
            assert admitted[0]==wal.recover()[0][1]
        finally:wal.close()
    asyncio.run(run())
