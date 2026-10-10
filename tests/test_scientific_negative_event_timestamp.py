import asyncio
from grid.scientific_event_router import route_market_event


class NoSideEffects:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected agent state access: {name}")


def test_negative_timestamp_is_rejected_without_agent_or_db_side_effects():
    result = asyncio.run(route_market_event(
        NoSideEffects(), NoSideEffects(), "BTCUSDT", -1,
        "trade_tape_250ms", {"close": 100}, "train", 42))
    assert result == {
        "processed": False, "reason": "invalid_event_timestamp", "scheduled": 0
    }
