import asyncio

import pytest

from grid import microstructure as module


def test_null_symbol_collection_rejected_before_network(monkeypatch):
    def fail(*args,**kwargs):
        raise AssertionError("null symbol collection must not connect")
    monkeypatch.setattr(module.websockets,"connect",fail)
    with pytest.raises(ValueError,match="symbols"):
        asyncio.run(module.MicrostructureCollector(None).run_batch(None))
