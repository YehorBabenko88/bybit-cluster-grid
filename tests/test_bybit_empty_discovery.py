"""An empty Bybit discovery must not retire the entire known instrument universe."""
import asyncio
import pytest
from grid.bybit import linear_symbols


class FakeResponse:
    status=200
    headers={}
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    def raise_for_status(self):pass
    async def json(self,**kwargs):
        return {"retCode":0,"result":{"list":[],"nextPageCursor":""}}


class FakeSession:
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    def get(self,*args,**kwargs):return FakeResponse()


def test_empty_successful_discovery_is_rejected(monkeypatch):
    monkeypatch.setattr("grid.bybit.aiohttp.ClientSession",FakeSession)
    with pytest.raises(RuntimeError,match="empty active linear universe"):
        asyncio.run(linear_symbols("https://example.invalid",max_attempts=1))
