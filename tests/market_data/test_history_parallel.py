# Source Meta82 test_history_parallel.py; canonical import transfer.
import asyncio

import pytest

from market_data.history_parallel import bounded_map


@pytest.mark.asyncio
async def test_parallelism_bounded_and_results_ordered():
    active = peak = 0

    async def worker(value):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.001 * (value % 3))
            return value * 2
        finally:
            active -= 1

    results = await bounded_map(list(range(40)), worker, concurrency=5)
    assert peak <= 5
    assert peak > 1
    assert [item.value for item in results] == [x * 2 for x in range(40)]


@pytest.mark.asyncio
async def test_failure_isolated_and_remaining_work_completes():
    async def worker(value):
        if value == 2:
            raise RuntimeError("bad archive")
        return value

    results = await bounded_map([1, 2, 3], worker, concurrency=2)
    assert results[0].value == 1
    assert isinstance(results[1].error, RuntimeError)
    assert results[2].value == 3


@pytest.mark.asyncio
async def test_cancellation_drains_workers():
    active = 0

    async def worker(value):
        nonlocal active
        active += 1
        try:
            await asyncio.sleep(30)
        finally:
            active -= 1

    task = asyncio.create_task(bounded_map(list(range(20)), worker, concurrency=3))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0
