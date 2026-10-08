import asyncio

import pytest

from grid import microstructure as module


@pytest.mark.parametrize("invalid",[None,0,True,"","BTC.USDT","BTC USDT","BTC/USDT","БТК","BTC_USDT"])
def test_invalid_symbol_rejected_before_network(monkeypatch,invalid):
    def no_connect(*args,**kwargs):
        raise AssertionError("invalid symbol must not connect")
    monkeypatch.setattr(module.websockets,"connect",no_connect)
    with pytest.raises(ValueError,match="symbols"):
        asyncio.run(module.MicrostructureCollector(None).run_batch(["BTCUSDT",invalid]))


def test_empty_symbols_still_return_without_network(monkeypatch):
    def no_connect(*args,**kwargs):
        raise AssertionError("empty symbols must not connect")
    monkeypatch.setattr(module.websockets,"connect",no_connect)
    asyncio.run(module.MicrostructureCollector(None).run_batch([]))
