import asyncio
from collections import defaultdict

import pytest

from grid import microstructure as module


@pytest.mark.parametrize("invalid",[
    {},
    {"BTCUSDT": 1},
    {"BTCUSDT": 1, "ETHUSDT": 2},
    defaultdict(int, {"BTCUSDT": 1}),
])
def test_mapping_rejected_as_symbol_collection(monkeypatch,invalid):
    def fail(*args,**kwargs):
        raise AssertionError("mapping must not connect")
    monkeypatch.setattr(module.websockets,"connect",fail)
    with pytest.raises(ValueError,match="symbols"):
        asyncio.run(module.MicrostructureCollector(None).run_batch(invalid))
