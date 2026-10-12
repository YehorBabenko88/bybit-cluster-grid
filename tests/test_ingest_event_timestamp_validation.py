import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from grid import coordinator


@pytest.mark.parametrize("bad_ts", [True, None, "not-a-time", {}, [], -1, 253402300800000])
def test_ingest_event_invalid_timestamp_is_client_error(monkeypatch, bad_ts):
    async def scenario():
        fake_db=SimpleNamespace(pool=object(),insert_event=AsyncMock())
        monkeypatch.setattr(coordinator,"db",fake_db)
        monkeypatch.setattr(coordinator,"authenticate_agent",AsyncMock(return_value=True))
        monkeypatch.setattr(coordinator,"runtime_state",AsyncMock(return_value={"state":"ACTIVE"}))
        with pytest.raises(HTTPException) as exc:
            await coordinator.ingest_event(
                {"symbol":"BTCUSDT","event_type":"trade_tape_250ms","event_ts":bad_ts,"payload":{}},
                x_node_id="node-1",x_node_credential="valid",
            )
        assert exc.value.status_code==400
        fake_db.insert_event.assert_not_awaited()

    asyncio.run(scenario())
