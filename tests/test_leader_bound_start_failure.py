import asyncio
import pytest

from grid.leader_bound_service import LeaderBoundService


def test_failed_singleton_start_clears_epoch_and_allows_retry():
    async def scenario():
        calls = []
        async def start(epoch):
            calls.append(epoch)
            if len(calls) == 1:
                raise RuntimeError("startup failed")
        async def stop():
            return None
        service = LeaderBoundService(start, stop)
        with pytest.raises(RuntimeError, match="startup failed"):
            await service.gain(7)
        assert service.epoch is None
        assert not service.running
        await service.gain(8)
        assert service.epoch == 8
        assert service.running
    asyncio.run(scenario())


def test_cancelled_singleton_start_clears_epoch():
    async def scenario():
        async def start(epoch):
            raise asyncio.CancelledError()
        async def stop():
            return None
        service = LeaderBoundService(start, stop)
        with pytest.raises(asyncio.CancelledError):
            await service.gain(7)
        assert service.epoch is None
        assert not service.running
    asyncio.run(scenario())
