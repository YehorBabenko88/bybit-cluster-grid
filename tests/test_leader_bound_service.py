import asyncio

import pytest

from grid.leader_bound_service import LeaderBoundService


def test_epoch_change_requires_prior_stop():
    async def scenario():
        started=[]
        stopped=[]
        async def start(epoch):started.append(epoch)
        async def stop():stopped.append(True)
        service=LeaderBoundService(start,stop)
        await service.gain(10)
        await service.gain(10)
        with pytest.raises(RuntimeError,match="epoch changed"):
            await service.gain(11)
        assert started==[10]
        await service.lose()
        await service.gain(11)
        assert started==[10,11] and stopped==[True]
    asyncio.run(scenario())


def test_failed_start_does_not_mark_service_running():
    async def scenario():
        attempts=[]
        async def start(epoch):
            attempts.append(epoch)
            if len(attempts)==1:
                raise RuntimeError("startup failed")
        async def stop():pass
        service=LeaderBoundService(start,stop)
        with pytest.raises(RuntimeError,match="startup failed"):
            await service.gain(7)
        assert not service.running and service.epoch is None
        await service.gain(7)
        assert service.running and service.epoch==7
    asyncio.run(scenario())


def test_failed_stop_preserves_running_state_for_retry():
    async def scenario():
        stops=[]
        async def start(epoch):pass
        async def stop():
            stops.append(True)
            if len(stops)==1:
                raise RuntimeError("shutdown failed")
        service=LeaderBoundService(start,stop)
        await service.gain(2)
        with pytest.raises(RuntimeError,match="shutdown failed"):
            await service.lose()
        assert service.running and service.epoch==2
        await service.lose()
        assert not service.running and service.epoch is None
        assert len(stops)==2
    asyncio.run(scenario())


def test_partial_start_is_cleaned_up_before_retry():
    async def scenario():
        events=[]
        async def start(epoch):
            events.append(("start",epoch))
            if len(events)==1:
                raise RuntimeError("partial startup")
        async def stop():events.append(("stop",None))
        service=LeaderBoundService(start,stop)
        with pytest.raises(RuntimeError,match="partial startup"):
            await service.gain(1)
        assert events==[("start",1),("stop",None)]
        await service.gain(2)
        assert events[-1]==("start",2)
    asyncio.run(scenario())
