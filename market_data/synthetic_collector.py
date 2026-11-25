"""Finite synthetic raw receive from Grid3bf; no live/default Worker mode.

Reuses canonical exact Trade parser and rawv2 recorder/sink. No new writer,
scientific pipeline, transport or source authority is defined here.
"""
import asyncio
from .public_trades import decode_frame,parse_trades,MAX_FRAME_BYTES
from .raw_capture import RawCaptureError,RawCaptureRecorder

SYNTHETIC_COLLECTOR_PROFILE='market_data.synthetic-collector.v1'

class SyntheticCollector:
    def __init__(self,*,profile,raw_capture_factory):
        if type(profile) is not str or profile!=SYNTHETIC_COLLECTOR_PROFILE:
            raise ValueError('SYNTHETIC_COLLECTOR_PROFILE_INVALID')
        if not callable(raw_capture_factory):raise ValueError('SYNTHETIC_COLLECTOR_FACTORY_REQUIRED')
        self.profile=profile
        self.raw_capture_factory=raw_capture_factory
        self.raw_capture_failure=None
        self._offline_used=False

    def _raw_capture_for(self,symbol,endpoint):
        factory=getattr(self,'raw_capture_factory',None)
        capture=None if factory is None else factory(symbol,endpoint)
        if factory is not None and (not isinstance(capture,RawCaptureRecorder) or not capture.matches(symbol,endpoint)):
            raise RawCaptureError('RAW_CAPTURE_SOURCE_BINDING_INVALID')
        return capture


    async def _record_received_frame(self,raw,capture):
        ref=None if capture is None else await capture.frame(raw)
        return raw,ref


    async def receive_offline(self,frames,*,symbol,endpoint,observed_at_ms):
        """One finite synthetic receive, never provider admission or a run mode.

        Uses the same raw-before-decode hook and existing trade parser. Results
        remain local observations, not publication or a historical checkpoint.
        """
        if self.profile != SYNTHETIC_COLLECTOR_PROFILE:
            raise RuntimeError('COLLECTOR_OFFLINE_PROFILE_REQUIRED')
        if (type(frames) is not tuple or not 1<=len(frames)<=4
                or endpoint!='synthetic://bybit/linear'
                or type(symbol) is not str or symbol!='BTCUSDT'
                or type(observed_at_ms) is not int or not 0<observed_at_ms<2**63):
            raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
        total=0
        for raw in frames:
            if type(raw) not in (str,bytes):raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            if len(raw)>MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            size=len(raw.encode('utf-8')) if type(raw) is str else len(raw)
            if size>MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            total+=size
        if total>4*MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
        if self._offline_used:raise RuntimeError('COLLECTOR_OFFLINE_ALREADY_USED')
        self._offline_used=True
        capture=self._raw_capture_for(symbol,endpoint)
        if capture is None or capture._source_kind!='SYNTHETIC':
            raise RawCaptureError('RAW_CAPTURE_SOURCE_BINDING_INVALID')
        capture.begin_connection()
        batches=[]
        try:
            for raw in frames:
                raw,ref=await self._record_received_frame(raw,capture)
                try:
                    message,_=decode_frame(raw)
                    trades=parse_trades(message,symbol,observed_at_ms)
                except ValueError:
                    await capture.gap('frame_invalid',ref)
                    continue
                await capture.validated(ref,exchange_event_ms=max((t.ts_ms for t in trades),default=None))
                batches.append(tuple(trades))
            await capture.disconnect('normal_stop')
        except BaseException as error:
            self.raw_capture_failure='SYNTHETIC_CAPTURE_UNCERTAIN'
            try:
                await capture.disconnect('cancelled' if isinstance(error,asyncio.CancelledError) else 'transport_error')
            except BaseException as cleanup:
                error.add_note('capture disconnect outcome unknown: '+type(cleanup).__name__)
            raise
        return {'batches':tuple(batches),'metrics':capture.metrics(),'source_kind':'SYNTHETIC',
                'provider_sends':0,'execution_authority':False}
