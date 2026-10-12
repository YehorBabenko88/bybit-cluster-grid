import asyncio

from grid.pressure import PressureController, CRITICAL, NORMAL
from grid.worker import Worker


def test_single_assignment_recovers_after_being_fully_drained_offline():
    async def scenario():
        worker=object.__new__(Worker)
        worker.wanted={'BTCUSDT'};worker.micro_wanted={'BTCUSDT'}
        worker.pressure_drained=set();worker.operator_stopped=False;worker.bootstrap_paused=False
        worker.pressure=PressureController(state=CRITICAL)
        reconciles=[]
        async def reconcile(): reconciles.append(set(worker.wanted))
        worker.reconcile=reconcile
        await worker._apply_local_pressure()
        assert worker.wanted==set() and worker.pressure_drained=={'BTCUSDT'}
        worker.pressure.state=NORMAL
        await worker._apply_local_pressure()
        assert worker.wanted=={'BTCUSDT'} and worker.pressure_drained==set()
        assert reconciles==[set(),{'BTCUSDT'}]
    asyncio.run(scenario())


def test_offline_recovery_preserves_an_operator_stop():
    async def scenario():
        worker=object.__new__(Worker)
        worker.wanted=set();worker.micro_wanted=set();worker.pressure_drained={'BTCUSDT'}
        worker.operator_stopped=True;worker.bootstrap_paused=False
        worker.pressure=PressureController(state=NORMAL)
        async def reconcile(): raise AssertionError('operator STOP must not resume streams')
        worker.reconcile=reconcile
        await worker._apply_local_pressure()
        assert worker.wanted==set()
    asyncio.run(scenario())
