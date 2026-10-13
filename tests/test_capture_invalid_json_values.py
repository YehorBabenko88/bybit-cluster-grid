import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from grid.micro_event_storage import MicroEventStorage


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_capture_cannot_poison_ordered_wal(value):
    async def run():
        sink=MicroEventStorage.__new__(MicroEventStorage)
        sink.replay_done=asyncio.Event();sink.replay_done.set()
        sink.spool=SimpleNamespace(ratio=lambda:0,append=AsyncMock(return_value=1))
        sink.write_queue=SimpleNamespace(put=AsyncMock())
        sink._enqueue_lock=asyncio.Lock()
        with pytest.raises(ValueError):
            await sink.insert_event('BTCUSDT',1,'orderbook_capture_evidence',{'events':[{'seq':value}]})
        sink.spool.append.assert_not_awaited()
        sink.write_queue.put.assert_not_awaited()
    asyncio.run(run())
