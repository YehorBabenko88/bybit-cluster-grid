import asyncio

from grid.db_observer import DatabaseObserver


def test_notification_during_reconciliation_triggers_immediate_second_pass():
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def reconcile():
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()

        observer = DatabaseObserver(None, reconcile, poll_seconds=3600)
        task = asyncio.create_task(observer.run())
        try:
            await asyncio.wait_for(started.wait(), 1)
            observer._notify()
            release.set()
            for _ in range(100):
                if calls >= 2:
                    break
                await asyncio.sleep(0.01)
            assert calls >= 2, "notification during reconciliation must not be lost"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
