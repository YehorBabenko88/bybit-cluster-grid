import pytest
from meta_analyse.exchange import BybitPublic

@pytest.mark.asyncio
async def test_ranking_liquid_only():
    api = BybitPublic()
    async def fake_get(path, params=None):
        return {"list": [
            {"symbol":"AAAUSDT", "turnover24h":"900000", "lastPrice":"300", "prevPrice24h":"100"},
            {"symbol":"BBBUSDT", "turnover24h":"2000000", "lastPrice":"120", "prevPrice24h":"100"},
            {"symbol":"CCCUSDT", "turnover24h":"3000000", "lastPrice":"105", "prevPrice24h":"100"}]}
    api.get = fake_get
    assert await api.top_volatile(2) == ["BBBUSDT", "CCCUSDT"]
    await api.close()
