import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from grid.collection_ownership import OwnedSink, local_grants


def test_late_reply_cannot_extend_lease_or_relabel_old_sink():
    grants=local_grants({"ownership_protocol":1,"ownership":{"BTCUSDT":{
        "generation":3,"session":"s","ttl_seconds":5}}},"s",100,now=106)
    assert grants=={}


def test_immutable_sink_preserves_generation_before_wal_append():
    async def run():
        storage=type("Storage",(),{"save":AsyncMock()})()
        grants={"BTCUSDT":{"generation":3,"session":"s","deadline":time.monotonic()+10}}
        sink=OwnedSink(storage,grants)
        grants["BTCUSDT"]["generation"]=4
        await sink.save({"symbol":"BTCUSDT"})
        assert storage.save.call_args.kwargs["ownership"]["generation"]==3
    asyncio.run(run())


def test_expired_collector_cannot_append_live_data():
    async def run():
        storage=type("Storage",(),{"save":AsyncMock()})()
        sink=OwnedSink(storage,{"BTCUSDT":{"generation":3,"session":"s","deadline":0}})
        with pytest.raises(ValueError,match="expired"):
            await sink.save({"symbol":"BTCUSDT"})
        storage.save.assert_not_awaited()
    asyncio.run(run())
