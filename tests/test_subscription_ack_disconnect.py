import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self, frames):
        self.frames=list(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def send(self, raw):
        return None

    async def recv(self):
        if self.frames:
            item=self.frames.pop(0)
            if isinstance(item,BaseException):
                raise item
            return json.dumps(item)
        raise asyncio.CancelledError


@pytest.mark.parametrize("failure",[ConnectionError("peer reset"),OSError("network down"),TimeoutError("read timed out")])
def test_disconnect_during_ack_retries_new_socket(monkeypatch,failure):
    async def scenario():
        first=Socket([failure])
        second=Socket([
            {"op":"subscribe","success":True},
            asyncio.CancelledError(),
        ])
        sockets=iter([first,second])
        connections=[]
        def connect(*a,**kw):
            socket=next(sockets)
            connections.append(socket)
            return socket
        monkeypatch.setattr(module.websockets,"connect",connect)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module,"backoff_delays",lambda:iter([0,0,0]))
        async def no_sleep(_):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_sleep)
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(None).run_batch(["BTCUSDT"])
        assert len(connections)==2
    asyncio.run(scenario())
