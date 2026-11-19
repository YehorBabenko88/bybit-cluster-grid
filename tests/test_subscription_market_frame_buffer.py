import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from grid import microstructure as module
from test_preack_buffer_discard_reconnect import DB, Socket


@pytest.mark.parametrize('overflow', [False, True])
def test_subscription_frames_buffered_before_ack(monkeypatch, overflow):
    async def scenario():
        db = DB()
        now = int(time.time() * 1000)
        count = 2001 if overflow else 2
        frames = [
            {'topic': 'tickers.BTCUSDT', 'ts': now + i,
             'data': {'lastPrice': str(100 + i)}} for i in range(count)
        ]
        ack = {'op': 'subscribe', 'success': True}

        class GatedSocket(Socket):
            async def recv(self):
                raw = await super().recv()
                assert not db.events
                return raw

        class Recorder:
            profile = SimpleNamespace(max_frame_bytes=1048576)

            def __init__(self):
                self.raw = []
                self.admitted = []
                self.retired = []

            def matches(self, symbol, endpoint):
                return symbol == 'BTCUSDT' and endpoint == module.settings.bybit_ws_url

            def begin_connection(self):
                pass

            async def frame(self, raw):
                self.raw.append(json.loads(raw))
                return len(self.raw)

            async def validated(self, ref, **metadata):
                self.admitted.append(ref)

            async def disconnect(self, reason):
                self.retired.append(reason)

        async def immediate(*args):
            pass

        recorder = Recorder()
        monkeypatch.setattr(module, 'RawCaptureRecorder', Recorder)
        monkeypatch.setattr(module, 'wait_for_internet', immediate)
        monkeypatch.setattr(module.asyncio, 'sleep', immediate)
        monkeypatch.setattr(module.websockets, 'connect', lambda *a, **k: GatedSocket([*frames, ack]))
        collector = module.MicrostructureCollector(
            db, snapshot_ms=1, raw_capture_factory=lambda *a: recorder,
        )
        if overflow:
            with pytest.raises(module.RawCaptureError, match='RAW_CAPTURE_TRANSPORT_STOP'):
                await collector.run_batch(['BTCUSDT'])
            assert recorder.raw == frames
            assert recorder.admitted == db.events == []
            assert recorder.retired == ['transport_error']
        else:
            with pytest.raises(asyncio.CancelledError):
                await collector.run_batch(['BTCUSDT'])
            assert recorder.raw == [*frames, ack]
            assert recorder.admitted == [3, 1, 2]
            assert [event[3]['last_price'] for event in db.events] == ['100', '101']
            assert recorder.retired == ['cancelled']

    asyncio.run(scenario())
