from datetime import datetime, timedelta, timezone
import pytest
from grid.barrier_simulator import simulate_barrier


def _bar(ts=0, **kwargs):
    value = {"ts": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=ts),
             "open": 100, "high": 101, "low": 99, "close": 100}
    value.update(kwargs)
    return value


def _signal(**kwargs):
    value = {"symbol": "BTC", "direction": "LONG", "entry_ref": 100}
    value.update(kwargs)
    return value


@pytest.mark.parametrize("direction", [None, "", "HOLD", "FLAT"])
def test_barrier_does_not_infer_direction_from_future_candles(direction):
    with pytest.raises(ValueError, match="explicit"):
        simulate_barrier(_signal(direction=direction), [_bar()], fee_bps=0)


@pytest.mark.parametrize("entry", [0, -10, float("nan"), float("inf"), True])
def test_invalid_entry_fails_closed(entry):
    with pytest.raises(ValueError):
        simulate_barrier(_signal(entry_ref=entry), [_bar()])


@pytest.mark.parametrize("overrides", [
    {"low": 102}, {"high": 98}, {"close": float("nan")},
    {"open": 0}, {"high": float("inf")},
])
def test_invalid_candle_is_rejected(overrides):
    with pytest.raises(ValueError):
        simulate_barrier(_signal(), [_bar(**overrides)])


def test_replayed_or_duplicate_candle_timestamp_is_rejected():
    with pytest.raises(ValueError, match="strictly increasing"):
        simulate_barrier(_signal(), [_bar(0), _bar(0)])


@pytest.mark.parametrize("kwargs", [
    {"tp_bps": 0}, {"sl_bps": -1}, {"fee_bps": float("nan")},
    {"slippage_bps": -1}, {"horizon_bars": 0}, {"notional": float("inf")},
])
def test_invalid_simulation_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        simulate_barrier(_signal(), [_bar()], **kwargs)


def test_explicit_short_direction_keeps_conservative_tie_behavior():
    result = simulate_barrier(_signal(direction="SHORT"), [_bar()],
                              tp_bps=50, sl_bps=50, fee_bps=0, slippage_bps=0)
    assert result["side"] == "SHORT"
    assert result["exit_reason"] == "SL_SAME_BAR"
    assert result["pnl"] < 0
