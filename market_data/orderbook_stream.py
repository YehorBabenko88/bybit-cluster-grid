"""Bounded public L2 recovery with canonical raw capture before publication.

Ported lifecycle from Meta82; no second Store/WAL, metric engine, or source
authentication claim. An uncertain capture outcome is terminal, never retried.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from types import MappingProxyType
import json
import logging
import random
import time
from math import isfinite
import websockets

from .collector import PUBLIC_ENDPOINT
from .orderbook import OrderBook
from .public_trades import decode_frame, MAX_FRAME_BYTES
from .raw_capture import RawCaptureRecorder, RawCaptureError

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class BookSnapshot:
    symbol: str
    bids: object
    asks: object
    update_id: int
    sequence: int
    valid: bool
    message_type: str | None = None
    connection_epoch: int = 0
    capture_sha256: str | None = None
    validation_sha256: str | None = None
    source_status: str = 'CALLER_SUPPLIED_UNATTESTED'
    execution_authority: bool = False
    trading_authorized: bool = False

    @classmethod
    def from_book(cls, book, message_type=None, *, epoch=0, capture_sha256=None, validation_sha256=None,
                  source_status='CALLER_SUPPLIED_UNATTESTED'):
        return cls(book.symbol, MappingProxyType(dict(book.bids)),
                   MappingProxyType(dict(book.asks)), book.update_id,
                   book.sequence, book.valid, message_type, epoch, capture_sha256, validation_sha256, source_status)

    def payload(self, event_time_ms):
        if type(event_time_ms) is not int or not 0 < event_time_ms < 2**63:
            raise ValueError('explicit provider event time required')
        return dict(schema='market_data.orderbook.snapshot.v1', symbol=self.symbol,
            bids=[[str(price), str(size)] for price, size in sorted(self.bids.items(), reverse=True)],
            asks=[[str(price), str(size)] for price, size in sorted(self.asks.items())],
            update_id=self.update_id, sequence=self.sequence, structurally_valid=self.valid,
            provider_event_time_ms=event_time_ms, connection_epoch=self.connection_epoch,
            capture_sha256=self.capture_sha256, validation_sha256=self.validation_sha256,
            source_status=self.source_status, execution_authority=False, trading_authorized=False)


class _ResubscribeRequired(ConnectionError):
    pass


class _ConsumerOutcomeUnknown(RuntimeError):
    pass


class OrderBookStream:
    def __init__(self, on_book, on_gap, *, capture_factory=None, depth=50,
                 url=PUBLIC_ENDPOINT, silence_timeout=90, backoff_base=1,
                 backoff_max=60, max_epochs=8, persist_timeout=20):
        if type(depth) is not int or depth not in (1, 50, 200, 500):
            raise ValueError('unsupported public orderbook depth')
        if url != PUBLIC_ENDPOINT:
            raise ValueError('only the canonical public provider endpoint is supported')
        if any(type(value) not in (int, float) or not isfinite(value)
               for value in (silence_timeout, backoff_base, backoff_max, persist_timeout)):
            raise ValueError('finite numeric reconnect settings required')
        if (type(max_epochs) is not int or not 1 <= max_epochs <= 8
                or not 0 < persist_timeout <= 20
                or not 0 < silence_timeout <= 90 or backoff_base <= 0
                or not backoff_base <= backoff_max <= 60):
            raise ValueError('invalid bounded reconnect configuration')
        if not callable(capture_factory):
            raise ValueError('DURABLE_CAPTURE_REQUIRED')
        self.on_book, self.on_gap = on_book, on_gap
        self.capture_factory = capture_factory
        self.depth, self.url = depth, url
        self.silence_timeout = silence_timeout
        self.backoff_base, self.backoff_max = backoff_base, backoff_max
        self.max_epochs, self.persist_timeout = max_epochs, persist_timeout
        self.connection_epoch = 0
        self.queue_limit = 4
        self.books = {}
        self._captures = {}

    async def _persist(self, operation):
        try:
            return await asyncio.wait_for(operation, timeout=self.persist_timeout)
        except TimeoutError:
            raise RawCaptureError('RAW_CAPTURE_PERSIST_OUTCOME_UNKNOWN') from None

    async def _callback(self, callback, *args):
        try:
            return await asyncio.wait_for(callback(*args), timeout=20)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise _ConsumerOutcomeUnknown('consumer acknowledgement outcome unknown') from None

    async def _gap(self, symbols, reason):
        await self._callback(self.on_gap, symbols, reason)

    def _reset(self):
        for book in self.books.values():
            book.reset()

    async def _disconnect(self, reason):
        for capture in self._captures.values():
            await self._persist(capture.disconnect(reason))

    async def run(self, symbols, stop):
        if type(symbols) not in (tuple, list) or not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols):
            raise ValueError('one connection requires one to ten distinct instruments')
        self.books = {symbol: OrderBook(symbol, max_levels=self.depth) for symbol in symbols}
        delay = self.backoff_base
        accepted = 0
        for _ in range(self.max_epochs):
            if stop.is_set():
                break
            self.connection_epoch += 1
            self._reset()
            self._captures = {}
            try:
                for symbol in symbols:
                    capture = self.capture_factory(symbol, self.url)
                    if not isinstance(capture, RawCaptureRecorder) or not capture.matches(symbol, self.url):
                        raise RawCaptureError('RAW_CAPTURE_FACTORY_INVALID')
                    capture.begin_connection()
                    self._captures[symbol] = capture
                await self._gap(symbols, 'orderbook reconnect requires fresh snapshots; source UNVERIFIED')
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=15,
                        max_queue=self.queue_limit, max_size=MAX_FRAME_BYTES, close_timeout=2, proxy=None) as ws:
                    await ws.send(json.dumps({'op': 'subscribe', 'args': [
                        f'orderbook.{self.depth}.{symbol}' for symbol in symbols]}))
                    subscribed = False
                    last_message = {symbol: time.monotonic() for symbol in symbols}
                    while not stop.is_set():
                        if any(time.monotonic() - stamp >= self.silence_timeout for stamp in last_message.values()):
                            raise _ResubscribeRequired('connected orderbook feed silent')
                        # End the bounded physical epoch before the recorder's
                        # control reserve is exhausted. This is not a retry of
                        # a terminal recorder/capacity/storage refusal.
                        if any(capture.metrics()['observation_attempts'] >= 10
                               for capture in self._captures.values()):
                            raise _ResubscribeRequired('bounded epoch requires fresh snapshots')
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(1, self.silence_timeout))
                        except asyncio.TimeoutError:
                            continue
                        try:
                            message, _ = decode_frame(raw)
                        except ValueError:
                            capture = self._captures[symbols[0]]
                            reference = await self._persist(capture.frame(raw))
                            await self._persist(capture.gap('frame_invalid', reference))
                            raise _ResubscribeRequired('malformed orderbook JSON') from None
                        topic = message.get('topic')
                        symbol = topic.rsplit('.', 1)[-1] if type(topic) is str else None
                        selected = symbol if symbol in self.books else symbols[0]
                        capture = self._captures[selected]
                        reference = await self._persist(capture.frame(raw))
                        if message.get('op') == 'subscribe':
                            if subscribed or message.get('success') is not True:
                                await self._persist(capture.gap('frame_invalid', reference))
                                raise _ResubscribeRequired('orderbook subscription rejected')
                            subscribed = True
                            continue
                        if type(topic) is not str or topic != f'orderbook.{self.depth}.{symbol}' or symbol not in self.books:
                            continue  # Watchdog remains per subscribed symbol.
                        if not subscribed:
                            await self._persist(capture.gap('frame_invalid', reference))
                            raise _ResubscribeRequired('orderbook arrived before subscription acknowledgement')
                        book = self.books[symbol]
                        timestamp_ms = message.get('ts')
                        if type(timestamp_ms) is not int or not 0 < timestamp_ms < 2**63:
                            book.reset()
                            await self._persist(capture.gap('frame_invalid', reference))
                            await self._gap([symbol], 'invalid orderbook timestamp')
                            raise _ResubscribeRequired('malformed orderbook timestamp')
                        if not book.apply(message):
                            await self._persist(capture.gap('sequence_invalid', reference))
                            await self._gap([symbol], 'invalid orderbook snapshot or delta')
                            raise _ResubscribeRequired('invalid orderbook; fresh snapshot required')
                        await self._persist(capture.validated(reference, exchange_event_ms=timestamp_ms,
                            sequence=book.sequence, update_id=book.update_id,
                            resync=message.get('type') == 'snapshot'))
                        last_message[symbol] = time.monotonic()
                        snapshot = BookSnapshot.from_book(book, message.get('type'),
                            epoch=self.connection_epoch, capture_sha256=reference.metadata_sha256,
                            validation_sha256=capture.metrics()['last_observation_readback_sha256'],
                            source_status='PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED')
                        await self._callback(self.on_book, symbol, snapshot, timestamp_ms)
                        accepted += 1
                        if message.get('type') == 'snapshot':
                            delay = self.backoff_base
                    await self._disconnect('normal_stop')
            except asyncio.CancelledError:
                self._reset()
                try:
                    await self._disconnect('cancelled')
                except Exception:
                    pass  # Preserve caller cancellation, never report an ACK.
                raise
            except (RawCaptureError, _ConsumerOutcomeUnknown):
                # Timeout can mean unknown storage/callback outcome. Never
                # reconnect around it or emit an accepted publication.
                self._reset()
                try:
                    await self._gap(symbols, 'capture outcome unknown; source UNVERIFIED')
                except Exception:
                    pass
                raise
            except Exception as error:
                self._reset()
                await self._disconnect('transport_error')
                reason = ('orderbook feed silent; source UNVERIFIED'
                    if type(error) is _ResubscribeRequired
                    and error.args == ('connected orderbook feed silent',)
                    else 'orderbook disconnected; source UNVERIFIED')
                await self._gap(symbols, reason)
                LOG.warning('Orderbook epoch recovery required', extra={
                    'event': 'orderbook_recovery', 'epoch': self.connection_epoch})
                if stop.is_set():
                    break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=min(
                        self.backoff_max, delay * random.uniform(0.8, 1.2)))
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, self.backoff_max)
        return {'schema': 'market_data.orderbook.capture.receipt.v1',
                'connection_epochs': self.connection_epoch, 'accepted_book_observations': accepted,
                'source_status': 'UNVERIFIED', 'coverage': 'UNKNOWN',
                'execution_authority': False, 'trading_authorized': False}
