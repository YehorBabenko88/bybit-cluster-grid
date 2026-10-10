"""Conservative OHLC barrier simulator for research-only outcomes.

Never infer the trading side from a candle observed after the signal.
"""
from math import isfinite


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(number) or (positive and number <= 0) or (nonnegative and number < 0):
        raise ValueError(f"{name} must be a finite number in the allowed range")
    return number


def _direction(signal, candle=None):
    direction = str(signal.get("direction") or "").upper()
    if direction in ("UP", "LONG", "BULL", "ABOVE"):
        return 1
    if direction in ("DOWN", "SHORT", "BEAR", "BELOW"):
        return -1
    # A missing/ambiguous direction cannot be reconstructed from future OHLC.
    raise ValueError("signal direction must be explicit before the first future candle")


def _cost(notional_bps, price):
    return abs(float(price)) * float(notional_bps) / 10000.0


def simulate_barrier(signal, candles, tp_bps=40, sl_bps=25, horizon_bars=60,
                     fee_bps=5.5, slippage_bps=1.5, notional=100.0):
    if not isinstance(horizon_bars, int) or isinstance(horizon_bars, bool) or horizon_bars <= 0:
        raise ValueError("horizon_bars must be a positive integer")
    tp_bps = _number(tp_bps, "tp_bps", positive=True)
    sl_bps = _number(sl_bps, "sl_bps", positive=True)
    fee_bps = _number(fee_bps, "fee_bps", nonnegative=True)
    slippage_bps = _number(slippage_bps, "slippage_bps", nonnegative=True)
    notional = _number(notional, "notional", positive=True)
    if not candles:
        return None
    rows = list(candles)[:horizon_bars]
    if not rows:
        return None
    side = _direction(signal)
    first = rows[0]
    reference = signal.get("entry_ref")
    entry = _number(first["open"] if reference is None else reference, "entry", positive=True)
    tp = entry * (1 + side * tp_bps / 10000.0)
    sl = entry * (1 - side * sl_bps / 10000.0)
    if tp <= 0 or sl <= 0 or not isfinite(tp) or not isfinite(sl):
        raise ValueError("invalid barrier prices")

    validated = []
    previous_ts = None
    for bar in rows:
        ts = bar["ts"]
        if previous_ts is not None and ts <= previous_ts:
            raise ValueError("candles must have strictly increasing timestamps")
        previous_ts = ts
        op = _number(bar["open"], "open", positive=True)
        hi = _number(bar["high"], "high", positive=True)
        lo = _number(bar["low"], "low", positive=True)
        close = _number(bar["close"], "close", positive=True)
        if lo > min(op, close) or hi < max(op, close) or lo > hi:
            raise ValueError("invalid OHLC candle")
        validated.append((ts, hi, lo, close))

    exit_price = validated[-1][3]
    exit_ts = validated[-1][0]
    reason = "HORIZON"
    max_fav = 0.0
    max_adv = 0.0
    for ts, hi, lo, close in validated:
        fav = (hi - entry) if side > 0 else (entry - lo)
        adv = (entry - lo) if side > 0 else (hi - entry)
        max_fav = max(max_fav, fav)
        max_adv = max(max_adv, adv)
        hit_tp = hi >= tp if side > 0 else lo <= tp
        hit_sl = lo <= sl if side > 0 else hi >= sl
        if hit_tp and hit_sl:
            exit_price, exit_ts, reason = sl, ts, "SL_SAME_BAR"
            break
        if hit_sl:
            exit_price, exit_ts, reason = sl, ts, "SL"
            break
        if hit_tp:
            exit_price, exit_ts, reason = tp, ts, "TP"
            break

    qty = notional / entry
    gross = (exit_price - entry) * side * qty
    fees = notional * fee_bps / 10000.0 + abs(exit_price * qty) * fee_bps / 10000.0
    slippage = notional * slippage_bps / 10000.0 + abs(exit_price * qty) * slippage_bps / 10000.0
    return {
        "signal_id": signal.get("signal_id"), "symbol": signal.get("symbol"),
        "setup_type": signal.get("setup_type"), "regime": signal.get("regime"),
        "event_ts": signal.get("event_ts"), "entry": entry, "exit": exit_price,
        "notional": notional, "quantity": qty, "initial_tp": tp, "initial_sl": sl,
        "exit_ts": exit_ts, "side": "LONG" if side > 0 else "SHORT", "exit_reason": reason,
        "pnl": gross, "fees": fees, "slippage": slippage,
        "mfe": max_fav * qty, "mae": -max_adv * qty, "bars": len(validated),
    }


async def load_forward_candles(pool, symbol, event_ts, horizon_bars):
    rows = await pool.fetch("""SELECT ts,open,high,low,close FROM candles_1m
      WHERE symbol=$1 AND ts>=$2 ORDER BY ts LIMIT $3""", symbol, event_ts, int(horizon_bars))
    return [dict(r) for r in rows]
