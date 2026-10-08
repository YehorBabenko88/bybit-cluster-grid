import asyncio

import pytest

from grid import microstructure as module


@pytest.mark.parametrize("invalid",[0,42,1.5,True,False,object()])
def test_noniterable_symbols_rejected_before_network(monkeypatch,invalid):
    def fail(*args,**kwargs):
        raise AssertionError("invalid symbol collection must not connect")
    monkeypatch.setattr(module.websockets,"connect",fail)
    with pytest.raises(ValueError,match="symbols"):
        asyncio.run(module.MicrostructureCollector(None).run_batch(invalid))
