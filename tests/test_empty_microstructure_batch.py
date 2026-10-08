import asyncio

from grid import microstructure as module


def test_empty_batch_skips_network_and_returns(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("empty batch must not open a WebSocket")
    async def unexpected_internet():
        raise AssertionError("empty batch must not wait for internet")
    monkeypatch.setattr(module.websockets,"connect",unexpected)
    monkeypatch.setattr(module,"wait_for_internet",unexpected_internet)
    asyncio.run(module.MicrostructureCollector(None).run_batch([]))
    asyncio.run(module.MicrostructureCollector(None).run_batch(()))
