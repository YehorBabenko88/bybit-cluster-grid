"""Durable raw Bybit ingestion pipeline; no inferred or synthetic trades."""
from __future__ import annotations
import asyncio
from .write_drain import drain_thread_write
import logging
from decimal import Decimal
from .raw_trades import RawTradeStream
from .raw_store import RawStore
from .integrity import ExecutionAggregator
from .health import HealthTracker

LOG = logging.getLogger(__name__)

class RawPipeline:
    def __init__(self, store, tick_sizes: dict[str, Decimal], on_closed=None, on_execution=None, on_gap=None):
        self.db = RawStore(store)
        self.aggregators = {s: ExecutionAggregator(tick) for s, tick in tick_sizes.items()}
        self.on_closed = on_closed
        self.on_execution = on_execution
        self.on_gap = on_gap
        self._locks = {symbol: asyncio.Lock() for symbol in tick_sizes}
        self.health = HealthTracker()
        self.stop_event = asyncio.Event()
        self.streams = []
        self.tasks = []

    async def execution(self, event):
        aggregator = self.aggregators.get(event.symbol)
        if aggregator is None:
            raise ValueError("unknown symbol or tick size")
        async with self._locks[event.symbol]:
            # Serialize persistence, aggregation and callbacks per instrument.
            # DB errors propagate; no execution is considered observed before commit.
            try:
                inserted = await drain_thread_write(self.db.save, event)
            except Exception:
                aggregator.gap([event.symbol], "database_error")
                self.health.gap(event.symbol)
                if self.on_gap:
                    await self.on_gap([event.symbol], "database_error")
                raise
            if not inserted:
                return
            self.health.record(event)
            before = len(aggregator.closed)
            aggregator.accept(event)
            quality = aggregator.quality.get(event.symbol)
            contiguous = bool(quality and quality.contiguous)
            if self.on_execution:
                await self.on_execution(event, contiguous=contiguous)
            for symbol, minute, status in aggregator.closed[before:]:
                if status == "observed_contiguous" and self.on_closed:
                    await self.on_closed(symbol, minute, status)

    async def gap(self, symbols, reason):
        # Mark in-memory continuity invalid even when database is unavailable.
        for symbol in symbols:
            if symbol in self.aggregators:
                async with self._locks[symbol]:
                    self.aggregators[symbol].gap([symbol], reason)
                    self.health.gap(symbol)
        if self.on_gap:
            await self.on_gap(symbols, reason)
        await drain_thread_write(self.db.gap, symbols, reason)

    async def start(self):
        if self.tasks:
            raise RuntimeError("pipeline already started")
        await drain_thread_write(self.db.initialize)
        symbols = list(self.aggregators)
        if not symbols:
            raise ValueError("no instruments")
        self.stop_event.clear()
        for offset in range(0, len(symbols), 10):
            stream = RawTradeStream(self.execution, self.gap)
            self.streams.append(stream)
            self.tasks.append(asyncio.create_task(stream.run(symbols[offset:offset+10], self.stop_event)))
        return self.tasks

    async def stop(self):
        self.stop_event.set()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.streams.clear()
