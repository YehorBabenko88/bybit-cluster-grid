import asyncio

import pytest

from grid import microstructure as module


@pytest.mark.parametrize("invalid",["BTCUSDT", "", b"BTCUSDT", b""])
def test_string_instead_of_symbol_collection_rejected(monkeypatch,invalid):
    def fail(*args,**kwargs):
        raise AssertionError("invalid symbol collection must not connect")
    monkeypatch.setattr(module.websockets,"connect",fail)
    with pytest.raises(ValueError,match="symbols"):
        asyncio.run(module.MicrostructureCollector(None).run_batch(invalid))
