"""Bounded parallel processing for independently downloaded history archives.

Do not use unbounded gather: memory, disk and API limits are shared.
Results retain input order; one archive failure does not cancel others.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class BatchOutcome:
    index: int
    value: object | None
    error: Exception | None


async def bounded_map(items: Sequence[T], worker: Callable[[T], Awaitable[R]],
                      concurrency: int = 4) -> list[BatchOutcome]:
    if type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ValueError("concurrency must be between 1 and 64")
    queue: asyncio.Queue[tuple[int, T]] = asyncio.Queue()
    for index, item in enumerate(items):
        queue.put_nowait((index, item))
    results: list[BatchOutcome | None] = [None] * len(items)

    async def consume():
        while True:
            try:
                index, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                results[index] = BatchOutcome(index, await worker(item), None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                results[index] = BatchOutcome(index, None, exc)
            finally:
                queue.task_done()

    tasks = [asyncio.create_task(consume()) for _ in range(min(concurrency, len(items)))]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    return results
