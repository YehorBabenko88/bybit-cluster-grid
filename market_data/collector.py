"""Bounded public trade capture, with persistence before any downstream use.

Reuses the canonical decoder and RawCaptureRecorder, without strategy, price
aggregation, mathematical feature pipelines, or alternate market writers.
"""
import asyncio
import json
import re
import time
from math import isfinite

from .public_trades import decode_frame, parse_trades, delivery_identity, MAX_FRAME_BYTES
from .raw_capture import RawCaptureRecorder, RawCaptureProfile, RawCaptureError
from .admission import startup_identity


PUBLIC_ENDPOINT = 'wss://stream.bybit.com/v5/public/linear'


async def public_connection(endpoint):
    if endpoint != PUBLIC_ENDPOINT:
        raise ValueError('only the canonical public provider endpoint is supported')
    import websockets
    return websockets.connect(endpoint, max_size=MAX_FRAME_BYTES, max_queue=4,
                              open_timeout=10, close_timeout=3, ping_interval=20,
                              ping_timeout=10, proxy=None)


class _AdmittedCaptureSink:
    """Grant check around the SAME supplied writer; no new store or journal."""
    def __init__(self,owner,sink):
        if not callable(getattr(sink,"store_capture",None)):raise ValueError("canonical capture sink required")
        self.owner=owner;self.sink=sink
    async def store_capture(self,**kwargs):
        self.owner._require_current_identity();facts=await self.sink.store_capture(**kwargs);self.owner._require_current_identity();return facts

class PublicTradeCollector:
    def __init__(self, sink, *, symbol, source_revision, connector=public_connection,
                 clock_ms=lambda: time.time_ns() // 1_000_000, max_frames=4, persist_timeout=20,
                 on_execution=None,on_subscription_ready=None,startup_admission=None):
        if type(symbol) is not str or re.fullmatch('[A-Z0-9]{2,30}', symbol) is None:
            raise ValueError('invalid capture instrument')
        if type(max_frames) is not int or not 1 <= max_frames <= 4:
            raise ValueError('bounded capture requires one to four application frames')
        if (type(source_revision) is not str
                or re.fullmatch('[0-9a-f]{40}', source_revision) is None):
            raise ValueError('exact producer source revision required')
        if on_execution is not None and not callable(on_execution):
            raise ValueError("execution consumer must be callable")
        if on_subscription_ready is not None and not callable(on_subscription_ready):
            raise ValueError("subscription readiness callback must be callable")
        self.startup_admission=startup_admission;self._identity=None
        self.on_subscription_ready=on_subscription_ready
        self.source_revision=source_revision
        self.on_execution=on_execution
        self._acknowledged={}
        self._execution_pending=False
        self._started=False
        self.symbol = symbol
        self.connector = connector
        self.clock_ms = clock_ms
        self.max_frames = max_frames
        if (type(persist_timeout) not in (int, float) or not isfinite(persist_timeout)
                or not 0 < persist_timeout <= 20):
            raise ValueError('invalid persistence deadline')
        self.persist_timeout = persist_timeout
        self.recorder = RawCaptureRecorder(
            _AdmittedCaptureSink(self,sink), instrument={'exchange': 'bybit', 'category': 'linear',
                              'symbol': symbol, 'instrument_version': '1'},
            producer_source_revision=source_revision,
            source_kind='PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED', endpoint=PUBLIC_ENDPOINT,
            profile=RawCaptureProfile(16, 4194304, MAX_FRAME_BYTES, 16384, 2))

    @staticmethod
    def _raise_if_cancelled():
        # wait_for may return an already-completed result after consuming the
        # exception while the caller task still has a cancellation request.
        try:task=asyncio.current_task()
        except RuntimeError:return
        if task is not None and task.cancelling():raise asyncio.CancelledError

    def _current(self):
        self._raise_if_cancelled()
        self._require_current_identity()

    def _require_current_identity(self):
        # Raw cancelled-disconnect cleanup still needs the same identity proof.
        # On Python3.12 wait_for can execute this sink in the cancelled owner.
        try:identity=startup_identity(self.startup_admission)
        except Exception:raise RawCaptureError("CURRENT_CAPTURE_ADMISSION_REQUIRED") from None
        if identity!=self._identity:raise RawCaptureError("CAPTURE_MANAGED_IDENTITY_CHANGED")

    def require_known_outcome(self):
        """Cancellation is not evidence that an in-flight commit did not occur."""
        if self._execution_pending:raise RawCaptureError('EXECUTION_COMMIT_OUTCOME_UNKNOWN')
        if self.recorder.metrics()['stop_reason']=='storage_unknown':raise RawCaptureError('RAW_CAPTURE_STORAGE_OUTCOME_UNKNOWN')

    async def _persist(self, operation):
        result=await asyncio.wait_for(operation, timeout=self.persist_timeout)
        self._raise_if_cancelled()
        return result

    async def run(self):
        self._raise_if_cancelled()
        if self._started:
            raise RawCaptureError("CAPTURE_INSTANCE_REUSE_REJECTED")
        self._started=True
        try:self._identity=startup_identity(self.startup_admission)
        except Exception:raise RawCaptureError("CURRENT_CAPTURE_ADMISSION_REQUIRED") from None
        self.recorder.begin_connection()
        accepted = 0
        subscribed = False
        try:
            self._current()
            connection = await self.connector(PUBLIC_ENDPOINT)
            self._current()
            async with connection as websocket:
                self._current()
                await websocket.send(json.dumps({'op': 'subscribe', 'args': ['publicTrade.' + self.symbol]}))
                for _ in range(self.max_frames):
                    self._current()
                    raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                    self._current()
                    reference = await self._persist(self.recorder.frame(raw))
                    try:
                        message, _ = decode_frame(raw)
                        if message.get('op') == 'subscribe':
                            if subscribed or message.get('success') is not True:
                                raise ValueError('public subscription refused')
                            subscribed = True
                            if self.on_subscription_ready is not None:
                                self._current()
                                await self._persist(self.on_subscription_ready(self.symbol,dict(
                                    schema="market_data.subscription-ready.v1",symbol=self.symbol,
                                    endpoint=PUBLIC_ENDPOINT,producer_source_revision=self.source_revision,
                                    frame_metadata_sha256=reference.metadata_sha256,
                                    readiness_scope="SUBSCRIPTION_ACK_CAPTURED_NOT_MARKET_COVERAGE",
                                    source_authenticity="UNKNOWN",coverage="UNKNOWN")))
                            continue
                        if not subscribed:
                            raise ValueError('public trades arrived before subscription acknowledgement')
                        trades = parse_trades(message, self.symbol, self.clock_ms())
                    except ValueError:
                        await self._persist(self.recorder.gap('frame_invalid', reference))
                        raise
                    pending={}
                    for trade in trades:
                        identity=delivery_identity(trade)
                        key=identity['delivery_key']; digest=identity['content_sha256']
                        if key in self._acknowledged and self._acknowledged[key]!=digest:
                            await self._persist(self.recorder.gap('frame_invalid', reference))
                            raise ValueError('conflicting acknowledged execution identity')
                        if key not in self._acknowledged:pending[key]=(trade,identity)
                    await self._persist(self.recorder.validated(reference))
                    if self.on_execution is not None:
                        for key,(trade,identity) in pending.items():
                            try:
                                self._current()
                                self._execution_pending=True
                                acknowledgement=await asyncio.wait_for(self.on_execution(trade,**identity),timeout=20)
                                self._current()
                                if (type(acknowledgement) is not dict
                                        or set(acknowledgement)!={'delivery_key','content_sha256','committed'}
                                        or acknowledgement.get('committed') is not True
                                        or acknowledgement.get('delivery_key')!=key
                                        or acknowledgement.get('content_sha256')!=identity['content_sha256']):
                                    raise ValueError('invalid execution acknowledgement')
                                self._execution_pending=False
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                raise RawCaptureError('EXECUTION_COMMIT_OUTCOME_UNKNOWN') from None
                            self._acknowledged[key]=identity['content_sha256']
                    accepted += len(trades)
                await self._persist(self.recorder.disconnect('normal_stop'))
        except asyncio.CancelledError:
            try:await self._persist(self.recorder.disconnect('cancelled'))
            except BaseException:pass  # Preserve caller cancellation; no cleanup ACK claim.
            raise
        except RawCaptureError:
            # Never reconnect around storage uncertainty or capacity refusal.
            raise
        except BaseException:
            await self._persist(self.recorder.disconnect('transport_error'))
            raise
        return {'schema': 'market_data.capture.receipt.v1',
                'accepted_trade_observations': accepted,
                'acknowledged_unique_executions': len(self._acknowledged),
                'capture': self.recorder.metrics(), 'coverage': 'UNKNOWN',
                'source_authenticity': 'NOT_INDEPENDENTLY_VERIFIED',
                'execution_authority': False, 'trading_authorized': False}
