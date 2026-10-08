"""Reconciliation must replace completed market tasks, not strand assigned symbols."""
import asyncio
from grid.worker import Worker


def test_reconcile_restarts_failed_trade_task():
    async def run():
        worker=Worker.__new__(Worker)
        worker.wanted={"BTCUSDT"}
        worker.meta={"BTCUSDT":{"tick_size":0.1}}
        worker.micro_wanted=set()
        worker.micro_signature=()
        worker.micro_tasks=[]
        calls=[]
        async def trade(symbol):
            calls.append(symbol)
            await asyncio.sleep(10)
        worker.trade_stream=trade
        async def fail():
            raise RuntimeError("collector exited")
        dead=asyncio.create_task(fail())
        await asyncio.gather(dead,return_exceptions=True)
        worker.trade_tasks={"BTCUSDT":dead}
        await worker.reconcile()
        replacement=worker.trade_tasks["BTCUSDT"]
        assert replacement is not dead
        await asyncio.sleep(0)
        assert calls==["BTCUSDT"]
        replacement.cancel()
        await asyncio.gather(replacement,return_exceptions=True)
    asyncio.run(run())


def test_reconcile_does_not_duplicate_live_trade_task():
    async def run():
        worker=Worker.__new__(Worker)
        worker.wanted={"BTCUSDT"}
        worker.meta={"BTCUSDT":{"tick_size":0.1}}
        worker.micro_wanted=set()
        worker.micro_signature=()
        worker.micro_tasks=[]
        live=asyncio.create_task(asyncio.sleep(10))
        worker.trade_tasks={"BTCUSDT":live}
        await worker.reconcile()
        assert worker.trade_tasks["BTCUSDT"] is live
        live.cancel()
        await asyncio.gather(live,return_exceptions=True)
    asyncio.run(run())
