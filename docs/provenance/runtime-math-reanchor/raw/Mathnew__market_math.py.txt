"""Pure Decimal market analytics migrated from Meta Analyse.

Preserves the source-defined HALF_UP tick bucket and explicit POC tie policies.
Does not ingest market data, run strategies, or assign trading authority.
"""
from collections.abc import Mapping
from decimal import Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN
from math import isfinite
import math


def _positive_finite_decimal(value, *, zero_allowed=False):
    if not isinstance(value, Decimal) or not value.is_finite() or (
        value < 0 if zero_allowed else value <= 0
    ):
        raise ValueError("finite Decimal required")
    return value


_PRICE_BUCKET_MAX_DIGITS = 128
_PRICE_BUCKET_MAX_ABS_EXPONENT = 1000


def price_bucket(price: Decimal, tick: Decimal, *, rounding="half_up") -> Decimal:
    """Round to a tick exactly, preserving its exponent (default HALF_UP).

    Positive finite operands accept up to 128 coefficient digits and an
    exponent from -1000 through 1000. Wider inputs raise ValueError before
    any integer scaling. The caller's Decimal context is unused. Explicit
    half_even preserves the data-builder tie rule without another kernel.
    """
    if type(rounding) is not str or rounding not in ("half_up", "half_even"):
        raise ValueError("unsupported price bucket rounding")
    price_parts = _positive_finite_decimal(price).as_tuple()
    tick_parts = _positive_finite_decimal(tick).as_tuple()
    for parts in (price_parts, tick_parts):
        if (len(parts.digits) > _PRICE_BUCKET_MAX_DIGITS
                or abs(parts.exponent) > _PRICE_BUCKET_MAX_ABS_EXPONENT):
            raise ValueError("price bucket Decimal outside supported domain")

    numerator = int(Decimal((0, price_parts.digits, 0)))
    tick_coefficient = int(Decimal((0, tick_parts.digits, 0)))
    denominator = tick_coefficient
    shift = price_parts.exponent - tick_parts.exponent
    if shift >= 0:
        numerator *= 10**shift
    else:
        denominator *= 10**-shift

    ticks, remainder = divmod(numerator, denominator)
    if (2 * remainder > denominator
            or 2 * remainder == denominator and (rounding == "half_up" or ticks % 2)):
        ticks += 1
    digits = Decimal(ticks * tick_coefficient).as_tuple().digits
    return Decimal((0, digits, tick_parts.exponent))


def volume_profile_poc(profile: dict[Decimal, Decimal], *, close: Decimal | None = None, tie_policy=None):
    """Executed-volume POC: nearest close/lowest price, or explicit first-seen ties.

    The Meta Minute (close provided) raises on an empty profile; the footprint\n    (close omitted) returns None. Reject ambiguous non-Decimal quantities.
    """
    if tie_policy not in (None, "first_seen") or tie_policy is not None and close is not None:
        raise ValueError("incompatible POC tie policy")
    if not isinstance(profile, dict):
        raise ValueError("volume profile must be a dict")
    if close is not None:
        _positive_finite_decimal(close)
    if not profile:
        if close is not None:
            raise ValueError("empty volume profile")
        return None
    for price, volume in profile.items():
        _positive_finite_decimal(price)
        _positive_finite_decimal(volume, zero_allowed=True)
    if close is None:
        if tie_policy == "first_seen":
            return max(profile, key=profile.get)
        return min(profile, key=lambda price: (profile[price].copy_negate(), price))
    highest_volume = max(profile.values())
    lower = upper = None
    for price, volume in profile.items():
        if volume != highest_volume:
            continue
        if price == close:
            return price
        if price < close:
            if lower is None or price > lower:
                lower = price
        elif upper is None or price < upper:
            upper = price
    if lower is None:
        return upper
    if upper is None:
        return lower
    return _nearest_bracket_price(lower, upper, close)


def _subtract_nearby(high, low):
    # The adjusted exponents are at most one apart. Aligning the coefficients
    # needs at most one extra digit, regardless of the absolute exponent.
    precision = max(len(high.as_tuple().digits), len(low.as_tuple().digits)) + 2
    exact = Context(prec=precision, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[Inexact])
    return exact.subtract(high, low)


def _nearest_bracket_price(lower, upper, close):
    # Upper wins only when (upper - close) + lower < close. Avoid constructing
    # an exact sum over arbitrary exponent gaps: compare magnitudes first.
    if upper.adjusted() > close.adjusted() + 1:
        return lower
    upper_gap = _subtract_nearby(upper, close)
    larger = max(upper_gap, lower)
    if larger >= close:
        return lower
    if larger.adjusted() < close.adjusted() - 1:
        return upper
    remaining = _subtract_nearby(close, larger)
    return upper if min(upper_gap, lower) < remaining else lower


def _market_amount(value):
    """Bound exact accumulated quantities/products before exponent alignment."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("MARKET_DECIMAL_DOMAIN")
    parts = value.as_tuple()
    if (len(parts.digits) > 4270 or abs(parts.exponent) > 2000
            or value and value.copy_abs().adjusted() > 2262):
        raise ValueError("MARKET_DECIMAL_DOMAIN")
    return value


def _market_context():
    # Bounded product/accumulator exponent span is at most 4263 digits.
    # 4300 retains exact sums/differences, including up to one million inputs.
    return Context(prec=4300, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[Inexact])


def _market_ratio(numerator, denominator, precision=28):
    if type(precision) is not int or precision not in (28, 96):
        raise ValueError("INVALID_RATIO_POLICY")
    return Context(prec=precision, rounding=ROUND_HALF_EVEN, Emin=MIN_EMIN,
                   Emax=MAX_EMAX, traps=[]).divide(numerator, denominator)


def exact_sum(values):
    """One-pass signed exact market-amount sum; <=1M bounded finite inputs.

    Inputs/results have <=4270 coefficient digits, exponent -2000..2000,
    adjusted magnitude <=2262. These bounds admit exact products of the
    128-digit/-1000..1000 market inputs and bounded accumulated quantities.
    No source trust or execution authority is conferred.
    """
    result = Decimal(0)
    exact = _market_context()
    try:
        source = iter(values)
    except TypeError as exc:
        raise ValueError("INVALID_MARKET_AMOUNTS") from exc
    for count, value in enumerate(source, 1):
        if count > MAX_STREAM_EVENTS:
            raise ValueError("MARKET_AMOUNT_LIMIT")
        result = exact.add(result, _market_amount(value))
    return _market_amount(result)


def wall_notional(price: Decimal, size: Decimal) -> Decimal:
    """Exact bounded notional; book membership/lifetime stay caller-owned."""
    _orderflow_decimal(_positive_finite_decimal(price))
    _orderflow_decimal(_positive_finite_decimal(size, zero_allowed=True))
    return _market_context().multiply(price, size)


def minute_volume_update(volume, quote_volume, buy_volume, sell_volume,
                         bucket_volume, price, size, side):
    """Pure five-total minute/profile update; DTO/time/OHLC remain caller-owned.

    Returns (volume, quote_volume, buy_volume, sell_volume, bucket_volume).
    Buy/1 and Sell/2 aliases are classified; other bounded strings are unknown.
    All operands are checked before any result is returned; no inputs mutate.
    """
    if type(side) is not str or len(side) > 16:
        raise ValueError("INVALID_MARKET_SIDE")
    prior = (volume, quote_volume, buy_volume, sell_volume, bucket_volume)
    for value in prior:
        _positive_finite_decimal(_market_amount(value), zero_allowed=True)
    amount = wall_notional(price, size)
    side = side.lower()
    return (exact_sum((volume, size)), exact_sum((quote_volume, amount)),
            exact_sum((buy_volume, size)) if side in ("buy", "1") else buy_volume,
            exact_sum((sell_volume, size)) if side in ("sell", "2") else sell_volume,
            exact_sum((bucket_volume, size)))


def footprint_cell_update(buy, sell, quantity, taker_side):
    """Exact executed-volume cell update; counters/provenance stay caller-owned."""
    for value in (buy, sell):
        _positive_finite_decimal(_market_amount(value), zero_allowed=True)
    _orderflow_decimal(_positive_finite_decimal(quantity, zero_allowed=True))
    if taker_side not in ("Buy", "Sell"):
        raise ValueError("invalid taker side")
    return (exact_sum((buy, quantity)), sell) if taker_side == "Buy" else (buy, exact_sum((sell, quantity)))


def executed_volume_delta(buy: Decimal, sell: Decimal) -> Decimal:
    """Exact signed taker delta; does not classify side or trust continuity."""
    for value in (buy, sell):
        _positive_finite_decimal(_market_amount(value), zero_allowed=True)
    return exact_sum((buy, sell.copy_negate()))


def tick_distance(price, level_price, tick_size, *, ratio_precision=28):
    """Absolute tick distance, finite 28-digit HALF_EVEN ratio policy."""
    for value in (price, level_price, tick_size):
        _orderflow_decimal(_positive_finite_decimal(value))
    gap = _market_context().subtract(price, level_price).copy_abs()
    return _market_ratio(gap, tick_size, ratio_precision)


def within_tick_distance(price, level_price, tick_size, proximity_ticks):
    """Exact proximity predicate; a rounded display ratio cannot admit data."""
    for value in (price, level_price, tick_size):
        _orderflow_decimal(_positive_finite_decimal(value))
    _orderflow_decimal(_positive_finite_decimal(proximity_ticks, zero_allowed=True))
    exact = _market_context()
    return exact.subtract(price, level_price).copy_abs() <= exact.multiply(tick_size, proximity_ticks)


def book_summary_metrics(bids, asks, tick):
    """Pure bounded book arithmetic; caller must qualify sequence/source.

    Returns (best_bid, best_ask, spread, bid_notional, ask_notional).
    Missing sides have None best price/spread; crossed books are refused.
    """
    _orderflow_decimal(_positive_finite_decimal(tick))
    if any(type(side) is not dict or len(side) > MAX_STREAM_BUCKETS for side in (bids, asks)):
        raise ValueError("INVALID_BOOK_LEVELS")
    amounts = []
    for side in (bids, asks):
        amounts.append(exact_sum(wall_notional(price, size) for price, size in side.items()))
    bid, ask = max(bids, default=None), min(asks, default=None)
    if bid is not None and ask is not None and bid >= ask:
        raise ValueError("CROSSED_BOOK")
    spread = _market_context().subtract(ask, bid) if bid is not None and ask is not None else None
    return bid, ask, spread, *amounts


def tape_velocity_metrics(events, level_price: Decimal, tick_size: Decimal,
                          window_ms: int, proximity_ticks: Decimal, now_ms: int,
                          *, observed_price: Decimal | None = None, ratio_precision=28):
    """Exact tape quantities; rates/distances use 28-digit HALF_EVEN ratios."""
    for value in (level_price, tick_size):
        _orderflow_decimal(_positive_finite_decimal(value))
    _orderflow_decimal(_positive_finite_decimal(proximity_ticks, zero_allowed=True))
    if (type(window_ms) is not int or not 0 < window_ms <= 2**63-1
            or type(now_ms) is not int or not 0 <= now_ms <= 2**63-1):
        raise ValueError("invalid tape window")
    if not isinstance(events, (tuple, list)) or len(events) > MAX_STREAM_EVENTS:
        raise ValueError("invalid tape events")
    buys = sells = Decimal(0)
    count = 0
    exact = _market_context()
    for timestamp_ms, price, quantity, side in events:
        if type(timestamp_ms) is not int or timestamp_ms < now_ms-window_ms or timestamp_ms > now_ms:
            raise ValueError("invalid tape timestamp")
        amount = wall_notional(price, quantity)
        if side not in ("Buy", "Sell"):
            raise ValueError("invalid tape side")
        # Compare exact quantities, never a rounded distance at a boundary.
        if within_tick_distance(price, level_price, tick_size, proximity_ticks):
            count += 1
            if side == "Buy":
                buys = exact_sum((buys, amount))
            else:
                sells = exact_sum((sells, amount))
    seconds = exact.divide(Decimal(window_ms), Decimal(1000))
    distance = None if observed_price is None else tick_distance(observed_price, level_price, tick_size, ratio_precision=ratio_precision)
    return (_market_ratio(Decimal(count), seconds, ratio_precision),
            _market_ratio(exact_sum((buys, sells)), seconds, ratio_precision), buys, sells, distance)


def flow_window_metrics(events, now_ms: int, window_seconds: int, *, ratio_precision=28):
    """Pure exact RollingFlow metrics. Input: (time_ms, notional, side)."""
    if (type(now_ms) is not int or not 0 <= now_ms <= 2**63-1
            or type(window_seconds) is not int or not 0 < window_seconds <= 2**63-1):
        raise ValueError("invalid flow window")
    if not isinstance(events, (tuple, list)) or len(events) > MAX_STREAM_EVENTS:
        raise ValueError("invalid flow events")
    buys = sells = total = Decimal(0)
    count = 0
    for timestamp_ms, notional, side in events:
        if type(timestamp_ms) is not int or timestamp_ms < 0 or type(side) is not str:
            raise ValueError("invalid flow event")
        _positive_finite_decimal(_market_amount(notional), zero_allowed=True)
        if not 0 <= now_ms-timestamp_ms <= window_seconds*1000:
            continue
        count += 1
        total = exact_sum((total, notional))
        if side in ("buy", "1"):
            buys = exact_sum((buys, notional))
        elif side in ("sell", "2"):
            sells = exact_sum((sells, notional))
    return {"turnover_usd": total, "trades": count, "buy_usd": buys,
            "sell_usd": sells, "trades_per_second": _market_ratio(Decimal(count), Decimal(window_seconds), ratio_precision)}


def wall_turnover_ratios(price: Decimal, size: Decimal, turnovers, *, ratio_precision=28):
    """Pure fixed-policy wall ratios; unknown source stays unverified."""
    amount = wall_notional(price, size)
    if not isinstance(turnovers, dict) or len(turnovers) > MAX_STREAM_BUCKETS:
        raise ValueError("invalid turnovers")
    return {"wall_usd": amount,
            "ratios": {window: _market_ratio(amount, max(Decimal(1), _positive_finite_decimal(_market_amount(total), zero_allowed=True)), ratio_precision)
                       for window,total in turnovers.items()},
            "observed_turnover": turnovers.copy()}


def historical_ohlc_directional_volume_valid(open,high,low,close,buy_volume,sell_volume):
    """Plain historical int/float OHLC/sign domain; never source authority.

    Preserve binary64-native finite/subnormal values and finite-convertible
    integers. No Decimal/Paper/lossless policy or foreign coercion is applied.
    """
    values=(open,high,low,close,buy_volume,sell_volume)
    if any(type(value) is not int and type(value) is not float for value in values):return False
    try:
        if not all(math.isfinite(value) for value in values):return False
        return 0<low<=min(open,close)<=max(open,close)<=high and min(buy_volume,sell_volume)>=0
    except (ValueError,OverflowError):return False


def historical_aggregate_integrity(row):
    """Historical binary64 partition/POC integrity; never source authentication.

    Preserves the source-defined math.isclose default rel_tol=1e-9 and
    abs_tol=1e-9 quantity checks, plus <=8*max(ulp(a),ulp(b)) price bounds.
    JSON byte caps, event time and provenance remain consumer-owned.
    """
    try:
        def number(v):return type(v) in (int,float) and math.isfinite(v)
        def boundary_equal(a,b):return abs(a-b)<=8*max(math.ulp(float(a)),math.ulp(float(b)))
        values=[row[k] for k in ('open','high','low','close','buy_volume','sell_volume','delta','poc_price')]
        if not all(number(v) for v in values):return False
        # ULP tolerance applies only inside the strictly positive price domain.
        # Subnormal rounding must never admit zero/negative market prices.
        if row['poc_price']<=0:return False
        if not historical_ohlc_directional_volume_valid(*(row[k] for k in ('open','high','low','close','buy_volume','sell_volume'))):return False
        if type(row['trade_count']) is not int or row['trade_count']<=0:return False
        levels=row['levels']
        if not isinstance(levels,list) or not 0<len(levels)<=10000:return False
        prices=set();buy=sell=trades=0
        for x in levels:
            if not all(number(x[k]) for k in ('price','buy_volume','sell_volume','delta','volume')):return False
            if x['price']<=0:return False
            if x['price'] in prices or not ((x['price']>=row['low'] or boundary_equal(x['price'],row['low'])) and (x['price']<=row['high'] or boundary_equal(x['price'],row['high']))):return False
            prices.add(x['price'])
            if min(x['buy_volume'],x['sell_volume'],x['volume'])<0:return False
            if not math.isclose(x['delta'],x['buy_volume']-x['sell_volume'],abs_tol=1e-9) or not math.isclose(x['volume'],x['buy_volume']+x['sell_volume'],abs_tol=1e-9):return False
            if any(type(x[k]) is not int or x[k]<0 for k in ('buy_count','sell_count')):return False
            buy+=x['buy_volume'];sell+=x['sell_volume'];trades+=x['buy_count']+x['sell_count']
        return (trades==row['trade_count'] and row['poc_price'] in prices and
                any(x['price']==row['poc_price'] and math.isclose(x['volume'],max(v['volume'] for v in levels),abs_tol=1e-9) for x in levels) and
                math.isclose(buy,row['buy_volume'],abs_tol=1e-9) and math.isclose(sell,row['sell_volume'],abs_tol=1e-9) and
                math.isclose(buy-sell,row['delta'],abs_tol=1e-9))
    except (KeyError,TypeError,ValueError,OverflowError):return False

def untouched_decimal_levels(closed_candles):
    """Meta core.untouched_levels numeric equivalence on verified CLOSED candles.

    Each item is (start_ms, high, low). Grid/Terminan must establish coverage,
    timeframe close, timestamp provenance and source authenticity separately.
    """
    if not isinstance(closed_candles, (tuple, list)):
        raise ValueError("INVALID_CANDLES")
    if len(closed_candles) > 20000:
        raise ValueError("CANDLE_LIMIT")
    normalized = []
    for candle in closed_candles:
        if not isinstance(candle, (tuple, list)) or len(candle) != 3:
            raise ValueError("INVALID_CANDLE")
        start, high, low = candle
        if type(start) is not int or start < 0 or start > 2**63-1:
            raise ValueError("INVALID_CANDLE_TIME")
        _positive_finite_decimal(high)
        _positive_finite_decimal(low)
        if high < low:
            raise ValueError("INVALID_CANDLE_RANGE")
        normalized.append((start, high, low))
    normalized.sort(key=lambda row: row[0])
    if any(a[0] == b[0] for a, b in zip(normalized, normalized[1:])):
        raise ValueError("DUPLICATE_CANDLE_TIME")
    return _untouched_price_sweep(normalized)


def _untouched_price_sweep(candles, tick_size=None):
    active = {}
    for start, high, low in candles:
        for key, level in list(active.items()):
            side, price, _ = level
            observed = high if side == "high" else low
            boundary = price
            if tick_size is not None:
                boundary = price - tick_size if side == "high" else price + tick_size
            touched = observed >= boundary if side == "high" else observed <= boundary
            if touched:
                del active[key]
        active[("high", high)] = ("high", high, start)
        active[("low", low)] = ("low", low, start)
    return tuple(active.values())


_LEVEL_PERIOD_MS = {"1h": 3600000, "4h": 14400000, "1d": 86400000, "1w": 604800000}


def _finite_level_number(value):
    if type(value) not in (int, float, Decimal, str):
        raise ValueError("invalid level number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid level number") from exc
    if not isfinite(number):
        raise ValueError("invalid level number")
    return number


def untouched_timeframe_levels(candles, timeframe, as_of_ms, *, tick_size=0, max_levels=200):
    """Compute levels from up to 20,000 caller-qualified t/h/l candles.

    t and as_of_ms are nonnegative integer UTC epoch milliseconds in int64.
    h, l and tick_size are finite binary64 values after conversion from int,
    float, Decimal or numeric string. complete must be Boolean when present.
    Missing complete retains legacy behavior. Incomplete candles and candles
    closing after as_of_ms are excluded. Source and coverage are caller-owned.
    """
    if (type(timeframe) is not str or timeframe not in _LEVEL_PERIOD_MS
            or type(as_of_ms) is not int or not 0 <= as_of_ms < 2**63
            or type(max_levels) is not int or not 1 <= max_levels <= 2000):
        raise ValueError("invalid level parameters")
    if not isinstance(candles, (list, tuple)) or len(candles) > 20000:
        raise ValueError("invalid candle collection")
    period = _LEVEL_PERIOD_MS[timeframe]
    tick_size = _finite_level_number(tick_size)
    if tick_size < 0:
        raise ValueError("invalid tick size")
    normalized = []
    for candle in candles:
        if not isinstance(candle, Mapping) or not {"t", "h", "l"} <= candle.keys():
            raise ValueError("invalid candle")
        start = candle["t"]
        complete = candle.get("complete", True)
        if type(start) is not int or not 0 <= start < 2**63 or type(complete) is not bool:
            raise ValueError("invalid candle time or completion")
        high = _finite_level_number(candle["h"])
        low = _finite_level_number(candle["l"])
        if high < low:
            raise ValueError("invalid candle range")
        if complete and start + period <= as_of_ms:
            normalized.append((start, high, low))
    normalized.sort(key=lambda row: row[0])
    active = _untouched_price_sweep(normalized, tick_size)
    # The legacy response groups surviving older levels by side before adding
    # the newest high/low pair and clipping to max_levels.
    survivors, latest = active[:-2], active[-2:]
    ordered = sorted(survivors, key=lambda level: level[0]) + list(latest)
    return [
        {"timeframe": timeframe, "side": side, "price": price,
         "origin_ms": start, "confirmed_ms": start + period}
        for side, price, start in ordered[-max_levels:]
    ]


# Two independent limits: the existing fixed-size batch contract stays at
# 20,000 rows; the explicit streaming contract may consume a larger bounded
# iterator but retains no raw event history and at most 20,000 bucket states.
MAX_ORDERFLOW_BATCH = 20_000
MAX_STREAM_EVENTS = 1_000_000
MAX_STREAM_BUCKETS = 20_000


def _orderflow_decimal(value):
    """Bound input before exponent alignment, including signed initial delta."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("ORDERFLOW_DECIMAL_DOMAIN")
    parts = value.as_tuple()
    if len(parts.digits) > 128 or abs(parts.exponent) > 1000:
        raise ValueError("ORDERFLOW_DECIMAL_DOMAIN")
    return value


def _orderflow_context():
    # Aligned inputs require at most 128 + 2*1000 digits. One million
    # events and the initial delta add at most seven digits. All sums and
    # differences fit exactly; Inexact is a fail-closed internal invariant.
    return Context(prec=2140, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[Inexact])


def _orderflow_price_floor(price, tick):
    """Exact positive FLOOR index; never round the quotient before flooring."""
    p, t = price.as_tuple(), tick.as_tuple()
    numerator = int(Decimal((0, p.digits, 0)))
    coefficient = int(Decimal((0, t.digits, 0)))
    denominator = coefficient
    shift = p.exponent - t.exponent
    if shift >= 0:
        numerator *= 10**shift
    else:
        denominator *= 10**-shift
    units = numerator // denominator
    return Decimal((0, Decimal(units * coefficient).as_tuple().digits, t.exponent))


def _new_orderflow_totals():
    return [Decimal(0), Decimal(0), Decimal(0), 0]


def _accumulate_orderflow(totals, price, volume, side, exact):
    """The one shared per-trade arithmetic for batch and streaming modes."""
    _positive_finite_decimal(price)
    _positive_finite_decimal(volume, zero_allowed=True)
    _orderflow_decimal(price)
    _orderflow_decimal(volume)
    if side == "buy":
        totals[0] = exact.add(totals[0], volume)
    elif side == "sell":
        totals[1] = exact.add(totals[1], volume)
    elif side == "unknown":
        totals[2] = exact.add(totals[2], volume)
    else:
        raise ValueError("unsupported trade side")
    totals[3] += 1


def _finish_orderflow(totals, initial_delta, exact):
    buy, sell, unknown, count = totals
    delta = exact.subtract(buy, sell)
    classified = exact.add(buy, sell)
    # A dimensionless ratio can repeat forever. Fix its public policy at
    # 28 significant digits, HALF_EVEN, independently of caller traps.
    ratio = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=MIN_EMIN,
                    Emax=MAX_EMAX, traps=[])
    return {"buy_volume": buy, "sell_volume": sell, "unknown_volume": unknown,
            "delta": delta, "cumulative_delta": exact.add(initial_delta, delta),
            "imbalance": ratio.divide(delta, classified) if classified else None,
            "trade_count": count}


def orderflow_volume_metrics(trades, initial_delta: Decimal = Decimal(0)):
    """Pure Meta orderflow_metrics.calculate arithmetic including unknown volume.

    Preserves the original bounded batch contract: at most 20,000 trade rows.
    """
    if not isinstance(initial_delta, Decimal) or not initial_delta.is_finite():
        raise ValueError("invalid initial delta")
    _orderflow_decimal(initial_delta)
    if not isinstance(trades, (tuple, list)) or len(trades) > MAX_ORDERFLOW_BATCH:
        raise ValueError("invalid trade batch")
    totals = _new_orderflow_totals()
    exact = _orderflow_context()
    for item in trades:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise ValueError("invalid trade")
        _accumulate_orderflow(totals, *item, exact)
    return _finish_orderflow(totals, initial_delta, exact)


def aggregate_orderflow_stream(trades, *, mode: str,
                               interval_ms: int | None = None,
                               tick_size: Decimal | None = None,
                               initial_delta: Decimal = Decimal(0)):
    """One-pass bounded-memory aggregation of a generator or finite iterable.

    Never materializes trade rows. Memory O(unique bucket count), strictly
    <=20,000 bucket states, independent of the number of input trades.
    Bucket keys are sorted after the stream ends. Volumes, deltas and price
    FLOOR bins are exact, independent of caller precision/traps. Decimal
    inputs accept <=128 coefficient digits and exponents -1000..1000.
    Imbalance uses 28 significant digits, HALF_EVEN (None if unclassified).
    Interleaved/late buckets retain the same exact totals.
    """
    if type(mode) is not str or mode not in ("time", "price"):
        raise ValueError("INVALID_AGGREGATE_MODE")
    if not isinstance(initial_delta, Decimal) or not initial_delta.is_finite():
        raise ValueError("INVALID_INITIAL_DELTA")
    _orderflow_decimal(initial_delta)
    exact = _orderflow_context()
    if mode == "time":
        if type(interval_ms) is not int or interval_ms <= 0:
            raise ValueError("INVALID_INTERVAL_MS")
    else:
        _positive_finite_decimal(tick_size)
        _orderflow_decimal(tick_size)
    try:
        source = iter(trades)
    except TypeError as exc:
        raise ValueError("INVALID_AGGREGATE_STREAM") from exc
    buckets = {}
    count = 0
    for entry in source:
        count += 1
        if count > MAX_STREAM_EVENTS:
            raise ValueError("STREAM_EVENT_LIMIT")
        if not isinstance(entry, (list, tuple)) or len(entry) != 4:
            raise ValueError("INVALID_AGGREGATE_TRADE")
        ts, price, volume, side = entry
        if type(ts) is not int or ts < 0:
            raise ValueError("INVALID_TRADE_CLOCK")
        _positive_finite_decimal(price)
        _positive_finite_decimal(volume, zero_allowed=True)
        _orderflow_decimal(price)
        _orderflow_decimal(volume)
        # Keep the original Meta grouping semantics: epoch-floor by timestamp
        # or ROUND_FLOOR price index. Never normalize price into HALF_UP bins.
        key = (ts // interval_ms * interval_ms if mode == "time" else
               _orderflow_price_floor(price, tick_size))
        totals = buckets.get(key)
        if totals is None:
            if len(buckets) >= MAX_STREAM_BUCKETS:
                raise ValueError("STREAM_BUCKET_LIMIT")
            totals = _new_orderflow_totals()
            buckets[key] = totals
        _accumulate_orderflow(totals, price, volume, side, exact)
    cumulative = initial_delta
    output = []
    for key in sorted(buckets):
        metrics = _finish_orderflow(buckets[key], cumulative, exact)
        cumulative = metrics["cumulative_delta"]
        output.append((key, metrics))
    return tuple(output)


def aggregate_orderflow(trades, *, mode: str, interval_ms: int | None = None,
                        tick_size: Decimal | None = None,
                        initial_delta: Decimal = Decimal(0)):
    """Legacy bounded batch API; do not weaken its 20,000-row admission."""
    if not isinstance(trades, (list, tuple)) or len(trades) > MAX_ORDERFLOW_BATCH:
        raise ValueError("INVALID_AGGREGATE_BATCH")
    return aggregate_orderflow_stream(trades, mode=mode, interval_ms=interval_ms,
                                      tick_size=tick_size, initial_delta=initial_delta)


def large_liquidity_levels(bids, asks, level_price: Decimal, tick_size: Decimal,
                           *, min_notional=Decimal("100000"),
                           min_relative=Decimal("5"),
                           max_distance_ticks=Decimal("50")):
    """Exact bounded liquidity selection; caller owns book validity/provenance.

    Price, size and thresholds use the 128-digit/-1000..1000 market domain.
    Notionals and median are exact; proximity and relative admission compare
    exact quantities. Returned distance/relative ratios use 28-digit HALF_EVEN.
    Sorting uses exact distance, then decreasing exact notional, with stable ties.
    """
    for value in (level_price, tick_size):
        _orderflow_decimal(_positive_finite_decimal(value))
    for value in (min_notional, min_relative, max_distance_ticks):
        _orderflow_decimal(_positive_finite_decimal(value, zero_allowed=True))
    if not isinstance(bids, dict) or not isinstance(asks, dict) or len(bids)+len(asks)>4096:
        raise ValueError("INVALID_LIQUIDITY_BOOK")
    entries = []
    for side, levels in (("bid", bids), ("ask", asks)):
        for price, size in levels.items():
            entries.append((side, price, wall_notional(price, size)))
    amounts = sorted(amount for _,_,amount in entries if amount>0)
    if not amounts:
        return ()
    exact = _market_context()
    mid = len(amounts)//2
    median = amounts[mid] if len(amounts)%2 else exact.divide(
        exact_sum((amounts[mid-1], amounts[mid])), Decimal(2))
    # Integer cross-products avoid either rounded division or precision loss
    # when the median's aligned coefficient spans thousands of digits.
    median_n, median_d = median.as_integer_ratio()
    threshold_n, threshold_d = min_relative.as_integer_ratio()
    results = []
    for side, price, amount in entries:
        amount_n, amount_d = amount.as_integer_ratio()
        if (amount >= min_notional
                and amount_n*median_d*threshold_d >= median_n*threshold_n*amount_d
                and within_tick_distance(price, level_price, tick_size, max_distance_ticks)):
            gap = exact.subtract(price, level_price).copy_abs()
            value = (side, price, amount, _market_ratio(gap, tick_size), _market_ratio(amount, median))
            results.append((gap, amount.copy_negate(), value))
    return tuple(value for _,_,value in sorted(results, key=lambda item: item[:2]))


def decimal_epoch_units(seconds, precision):
    """Floor nonnegative decimal epoch seconds to integer ms(3) or us(6).

    Accept only Decimal/string, finite 0<=seconds<253402300800; <=128
    coefficient digits and strings <=256 characters. Extreme tiny/zero
    exponents floor to zero before any scaling; nonzero results need only
    bounded powers (at most133 places for128 coefficient digits).
    Parsing and integer scaling never use or mutate the caller's context.
    This converts units only; timestamp source/causality remain caller-owned.
    """
    if type(precision) is not int or precision not in (3,6):
        raise ValueError('INVALID_EPOCH_PRECISION')
    if type(seconds) is str:
        if not 0<len(seconds)<=256:raise ValueError('INVALID_EPOCH_SECONDS')
        try:seconds=Decimal(seconds,context=Context(traps=[InvalidOperation]))
        except InvalidOperation as exc:raise ValueError('INVALID_EPOCH_SECONDS') from exc
    if type(seconds) is not Decimal or not seconds.is_finite() or not 0<=seconds<Decimal('253402300800'):
        raise ValueError('INVALID_EPOCH_SECONDS')
    parts=seconds.as_tuple()
    if len(parts.digits)>128:raise ValueError('EPOCH_DECIMAL_DOMAIN')
    if seconds.is_zero() or seconds.adjusted()+precision<0:return 0
    coefficient=int(Decimal((0,parts.digits,0)))
    shift=parts.exponent+precision
    return coefficient*10**shift if shift>=0 else coefficient//10**-shift


def _policy_decimal(value, *, positive=False, nonnegative=False):
    if type(value) is not Decimal or not value.is_finite():raise ValueError('PAPER_DECIMAL_DOMAIN')
    parts=value.as_tuple()
    if len(parts.digits)>128 or abs(parts.exponent)>4096:raise ValueError('PAPER_DECIMAL_DOMAIN')
    if positive and value<=0 or nonnegative and value<0:raise ValueError('PAPER_DECIMAL_DOMAIN')
    return value

def _paper_context():
    # Preserve each old default-context intermediate explicitly, without caller traps.
    return Context(prec=28,rounding=ROUND_HALF_EVEN,Emin=MIN_EMIN,Emax=MAX_EMAX,traps=[])

def _paper_side(side):
    if type(side) is not str or side not in ('long','short'):raise ValueError('INVALID_PAPER_SIDE')

def adverse_execution_price(price,side,bps,entry):
    """Pure adverse annotation arithmetic:28HALF_EVEN at each legacy step.

    All paper helpers accept finite Decimal operands <=128 coefficient digits,
    exponent +/-4096 (including derived position sizes), never caller context.
    No fills, state, signals, timestamps or execution authority are created.
    """
    _policy_decimal(price,positive=True);_policy_decimal(bps,nonnegative=True);_paper_side(side)
    if type(entry) is not bool or bps>=10000:raise ValueError('INVALID_PAPER_SLIPPAGE')
    c=_paper_context();fraction=c.divide(bps,Decimal(10000))
    if fraction>=1:raise ValueError('INVALID_PAPER_SLIPPAGE')
    adverse_up=(side=='long')==entry
    factor=c.add(Decimal(1),fraction) if adverse_up else c.subtract(Decimal(1),fraction)
    return _policy_decimal(c.multiply(price,factor),positive=True)

def paper_position_size(notional,entry):
    _policy_decimal(notional,positive=True);_policy_decimal(entry,positive=True)
    return _policy_decimal(_paper_context().divide(notional,entry),positive=True)

def paper_entry_fee(notional,rate):
    _policy_decimal(notional,positive=True);_policy_decimal(rate,nonnegative=True)
    if rate>=1:raise ValueError('INVALID_PAPER_FEE')
    return _policy_decimal(_paper_context().multiply(notional,rate),nonnegative=True)

def paper_stop_price(entry,side,stop_pct):
    """Preserves legacy nonnegative stop_pct, including signed stops above100%."""
    _policy_decimal(entry,positive=True);_policy_decimal(stop_pct,nonnegative=True);_paper_side(side)
    c=_paper_context();factor=c.subtract(Decimal(1),stop_pct) if side=='long' else c.add(Decimal(1),stop_pct)
    return _policy_decimal(c.multiply(entry,factor))

def paper_entry_side(price,poc,threshold):
    """Legacy inclusive short-first28digit threshold policy, not source trust."""
    _policy_decimal(price,positive=True);_policy_decimal(poc,positive=True);_policy_decimal(threshold,nonnegative=True)
    c=_paper_context()
    if price>=c.multiply(poc,c.add(Decimal(1),threshold)):return 'short'
    if price<=c.multiply(poc,c.subtract(Decimal(1),threshold)):return 'long'
    return None

def paper_fill_metrics(side,entry,exit,size,entry_fee,fee_rate):
    """Pure (gross,total_fees,net) using old sequential28digit intermediates."""
    _paper_side(side)
    for value in (entry,exit,size):_policy_decimal(value,positive=True)
    _policy_decimal(entry_fee,nonnegative=True);_policy_decimal(fee_rate,nonnegative=True)
    if fee_rate>=1:raise ValueError('INVALID_PAPER_FEE')
    c=_paper_context();difference=c.subtract(exit,entry) if side=='long' else c.subtract(entry,exit)
    gross=c.multiply(difference,size)
    exit_fee=c.multiply(c.multiply(size,exit),fee_rate)
    return tuple(_policy_decimal(value) for value in (gross,c.add(entry_fee,exit_fee),c.subtract(c.subtract(gross,entry_fee),exit_fee)))


def candle_ohlcv_valid(open,high,low,close,volume):
    """Pure Decimal OHLCV domain predicate; no source/coverage authentication.

    Finite Decimal prices must be strictly positive, volume nonnegative and
    OHLC ordered. Bounded128digit coefficients/exponent+/-4096; caller context
    unused. Identity, event time, completeness and provenance stay external.
    """
    try:
        for value in (open,high,low,close):_policy_decimal(value,positive=True)
        _policy_decimal(volume,nonnegative=True)
    except ValueError:return False
    return low<=min(open,close)<=max(open,close)<=high


def _paper_binary64(value):
    """Bounded legacy numeric conversion, with ambiguous booleans refused."""
    if type(value) not in (int,float,Decimal,str):raise ValueError('PAPER_BINARY64_DOMAIN')
    if type(value) is str and len(value)>256:raise ValueError('PAPER_BINARY64_DOMAIN')
    if type(value) is int and value.bit_length()>1024:raise ValueError('PAPER_BINARY64_DOMAIN')
    if type(value) is Decimal:_policy_decimal(value)
    try:result=float(value)
    except (ValueError,TypeError,OverflowError) as exc:raise ValueError('PAPER_BINARY64_DOMAIN') from exc
    if not math.isfinite(result):raise ValueError('PAPER_BINARY64_DOMAIN')
    return result

def paper_scale_value(value,size):
    """Pure legacy binary64 product; sizing mode/state remain caller-owned."""
    return _paper_binary64(_paper_binary64(value)*_paper_binary64(size))

def paper_size_multiplier(base,factor,step,cap):
    """Pure min(cap,base*factor**step); no sizing mode or loss-streak state."""
    base,factor,cap=map(_paper_binary64,(base,factor,cap))
    if type(step) is not int or not 0<=step<=1000000:raise ValueError('INVALID_PAPER_EXPONENT')
    try:return _paper_binary64(min(cap,base*factor**step))
    except OverflowError as exc:raise ValueError('PAPER_EXPONENT_OVERFLOW') from exc

def paper_net_pnl(pnl,fees,slippage):
    """Pure legacy sequential binary64 subtraction, not a trade ledger."""
    pnl,fees,slippage=map(_paper_binary64,(pnl,fees,slippage))
    return _paper_binary64((pnl-fees)-slippage)

def paper_equity_update(equity,peak,min_eq,max_dd,net):
    """Pure four-number update; account/ruin/portfolio policies stay external."""
    equity,peak,min_eq,max_dd,net=map(_paper_binary64,(equity,peak,min_eq,max_dd,net))
    updated=_paper_binary64(equity+net)
    new_peak=max(peak,updated);new_min=min(min_eq,updated)
    drawdown=_paper_binary64(new_peak-updated)
    return updated,new_peak,new_min,max(max_dd,drawdown)


# Causal paper v2: numerical values only; no journal, schedule or authority.
from typing import NamedTuple
import re as _numeric_re

class QuoteMetrics(NamedTuple):
    entry_price: Decimal
    exit_price: Decimal
    qty: Decimal
    signed_qty: Decimal
    gross_raw: Decimal
    gross_fill: Decimal
    slippage: Decimal
    fees: Decimal
    funding: Decimal
    net: Decimal

class AccountBalances(NamedTuple):
    cash: Decimal
    peak: Decimal
    reserved: Decimal
    available_cash: Decimal

class ReservationMetrics(NamedTuple):
    collateral: Decimal
    spread_bps: Decimal
    spread_exceeded: bool
    reservation_exceeded: bool
    cash_insufficient: bool
    drawdown_exceeded: bool

class BookTapeMetrics(NamedTuple):
    relative_volume: Decimal
    delta_ratio: Decimal
    base_width_fraction: Decimal
    proxy_poc: Decimal
    proxy_poc_distance: Decimal
    effort_anomaly: bool
    volume_confirmation: bool
    breakout_long: bool
    breakout_short: bool
    trend_long: bool
    trend_short: bool
    long_votes: int
    short_votes: int
    signal: int

def _causal_decimal(value, low, high):
    _orderflow_decimal(_policy_decimal(value))
    if not low<=value<=high:raise ValueError('CAUSAL_NUMERIC_DOMAIN')
    return value

def _causal_sequence(values, maximum=20000):
    if type(values) not in (list,tuple) or len(values)>maximum:raise ValueError('CAUSAL_BATCH_DOMAIN')
    return values

def _ratio_compare(numerator,denominator,threshold):
    if denominator<=0:raise ValueError('INVALID_RATIO')
    n,d=numerator.as_integer_ratio();a,b=denominator.as_integer_ratio();t,u=threshold.as_integer_ratio()
    difference=n*b*u-t*a*d
    return (difference>0)-(difference<0)

def paper_quote_metrics(side,raw_entry,raw_exit,notional,fee_bps,slippage_bps,funding_events):
    """V2 fixed28 HALF_EVEN intermediates; selected funding events are caller-owned.

    No binary64 parity claim. Fee order is qty*(entry+exit)*bps/10000.
    Numeric events are bounded to128; this does not verify their chronology.
    """
    _paper_side(side)
    for value in (raw_entry,raw_exit):_causal_decimal(value,Decimal('1e-12'),Decimal('1e12'))
    _causal_decimal(notional,Decimal('1e-9'),Decimal('1e12'))
    for value in (fee_bps,slippage_bps):_causal_decimal(value,Decimal(0),Decimal(1000))
    events=_causal_sequence(funding_events,128)
    for item in events:
        if type(item) not in (tuple,list) or len(item)!=2:raise ValueError('INVALID_FUNDING_EVENT')
        _causal_decimal(item[0],Decimal('1e-12'),Decimal('1e12'));_causal_decimal(item[1],Decimal(-1),Decimal(1))
    c=_paper_context();entry=adverse_execution_price(raw_entry,side,slippage_bps,True);exit=adverse_execution_price(raw_exit,side,slippage_bps,False)
    qty=paper_position_size(notional,entry);signed=qty if side=='long' else qty.copy_negate()
    raw=c.multiply(signed,c.subtract(raw_exit,raw_entry));fill=c.multiply(signed,c.subtract(exit,entry));slip=c.subtract(raw,fill)
    fee=c.divide(c.multiply(c.multiply(qty,c.add(entry,exit)),fee_bps),Decimal(10000));funding=Decimal(0)
    for mark,rate in events:funding=c.add(funding,c.multiply(c.multiply(signed,mark),rate))
    net=c.subtract(c.subtract(c.subtract(raw,slip),fee),funding)
    result=QuoteMetrics(entry,exit,qty,signed,raw,fill,slip,fee,funding,net)
    for value in result[2:]:
        if value.copy_abs()>Decimal('1e15'):raise ValueError('CAUSAL_RESULT_DOMAIN')
    return result

def paper_account_balances(initial_cash,settled_pnls,pending_pnls,collaterals):
    """Exact sums; ordered settled realizations affect peak, pending values do not."""
    _market_amount(initial_cash)
    if initial_cash<=0:raise ValueError('INVALID_INITIAL_CASH')
    for rows in (settled_pnls,pending_pnls,collaterals):
        _causal_sequence(rows)
        for value in rows:_market_amount(value)
    if any(value<0 for value in collaterals):raise ValueError('NEGATIVE_COLLATERAL')
    c=_market_context();cash=peak=initial_cash
    for value in settled_pnls:
        cash=c.add(cash,value);peak=max(peak,cash)
    cash=c.add(cash,exact_sum(pending_pnls));reserved=exact_sum(collaterals)
    return AccountBalances(cash,peak,reserved,c.subtract(cash,reserved))

def paper_reservation_metrics(cash,peak,reserved,bid,ask,notional,fee_bps,max_reserved,max_drawdown,max_spread_bps):
    """Exact admission predicates; spread display alone is rounded28 HALF_EVEN."""
    for value in (cash,peak,reserved,max_reserved):_market_amount(value)
    if peak<=0 or reserved<0 or max_reserved<0:raise ValueError('INVALID_RESERVATION')
    for value in (bid,ask):_causal_decimal(value,Decimal('1e-12'),Decimal('1e12'))
    if bid>ask:raise ValueError('CROSSED_BOOK')
    _causal_decimal(notional,Decimal('1e-9'),Decimal('1e12'));_causal_decimal(fee_bps,Decimal(0),Decimal(1000))
    _causal_decimal(max_drawdown,Decimal(0),Decimal(1));_orderflow_decimal(_policy_decimal(max_spread_bps,nonnegative=True))
    c=_market_context();collateral=c.multiply(notional,c.add(Decimal(1),c.divide(fee_bps,Decimal(10000))))
    spread_n=c.multiply(c.subtract(ask,bid),Decimal(10000));available=c.subtract(cash,reserved)
    return ReservationMetrics(collateral,_market_ratio(spread_n,bid),_ratio_compare(spread_n,bid,max_spread_bps)>0,c.add(reserved,collateral)>max_reserved,available<collateral,_ratio_compare(c.add(c.subtract(peak,available),collateral),peak,max_drawdown)>0)

def book_tape_research_metrics(close,buy,sell,past):
    """Exact v2 feature/vote predicates; first-seen POC, display6/8 HALF_EVEN.

    History timing/warmup/provenance remain external. Numeric past4..4096.
    """
    for value in (close,):_orderflow_decimal(_policy_decimal(value,positive=True))
    for value in (buy,sell):_orderflow_decimal(_policy_decimal(value,nonnegative=True))
    _causal_sequence(past,4096)
    if len(past)<4:raise ValueError('INSUFFICIENT_NUMERIC_HISTORY')
    for row in past:
        if type(row) not in (list,tuple) or len(row)!=2:raise ValueError('INVALID_NUMERIC_HISTORY')
        _orderflow_decimal(_policy_decimal(row[0],positive=True));_orderflow_decimal(_policy_decimal(row[1],nonnegative=True))
    c=_market_context();volume=c.add(buy,sell);delta=c.subtract(buy,sell);total=exact_sum([v for _,v in past])
    if volume<=0 or total<=0:raise ValueError('EMPTY_NUMERIC_VOLUME')
    relative_n=c.multiply(volume,Decimal(len(past)));previous=past[-1][0];prices=[p for p,_ in past];base=prices[-5:]
    width=c.subtract(max(base),min(base));direction=(close>previous)-(close<previous)
    rel12=_ratio_compare(relative_n,total,Decimal('1.2'))>=0
    effort=_ratio_compare(relative_n,total,Decimal('1.8'))>=0 and _ratio_compare(c.subtract(close,previous).copy_abs(),previous,Decimal('.0002'))<0
    directional=delta if direction==1 else delta.copy_negate() if direction==-1 else Decimal(0)
    confirmation=rel12 and _ratio_compare(directional,volume,Decimal('.2'))>=0
    narrow=_ratio_compare(width,previous,Decimal('.004'))<=0
    long=close>max(base) and narrow and rel12 and _ratio_compare(delta,volume,Decimal('.15'))>0
    short=close<min(base) and narrow and rel12 and _ratio_compare(delta,volume,Decimal('-.15'))<0
    profile={}
    for price,amount in past:profile[price]=c.add(profile.get(price,Decimal(0)),amount)
    poc=volume_profile_poc(profile,tie_policy='first_seen')
    tail=prices[-4:]+[close];up=sum(b>a for a,b in zip(tail,tail[1:]));down=sum(b<a for a,b in zip(tail,tail[1:]))
    trend_long=up>=3 and close>max(prices);trend_short=down>=3 and close<min(prices)
    lv=int(long)+int(trend_long)+int(confirmation and direction==1);sv=int(short)+int(trend_short)+int(confirmation and direction==-1)
    signal=1 if lv>=2 and sv==0 and not effort else -1 if sv>=2 and lv==0 and not effort else 0
    display=Context(prec=4300,rounding=ROUND_HALF_EVEN,Emin=MIN_EMIN,Emax=MAX_EMAX,traps=[])
    def rounded(n,d,places):return display.quantize(display.divide(n,d),Decimal((0,(1,),-places)))
    return BookTapeMetrics(rounded(relative_n,total,6),rounded(delta,volume,6),rounded(width,previous,8),poc,rounded(c.subtract(close,poc),close,8),effort,confirmation,long,short,trend_long,trend_short,lv,sv,signal)

def _paper_input_decimal(value,low,high):
    if type(value) not in (str,int,float):raise ValueError('INVALID_INPUT_NUMBER')
    if type(value) is str:
        if not 0<len(value)<=128 or _numeric_re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',value) is None:raise ValueError('INVALID_INPUT_NUMBER')
    if type(value) is int and value.bit_length()>101:raise ValueError('INVALID_INPUT_NUMBER')
    if type(value) is float and not math.isfinite(value):raise ValueError('INVALID_INPUT_NUMBER')
    try:exact=Decimal(str(value),context=Context(traps=[InvalidOperation]))
    except InvalidOperation as exc:raise ValueError('INVALID_INPUT_NUMBER') from exc
    if not exact.is_finite() or not low<=exact<=high:raise ValueError('INVALID_INPUT_NUMBER')
    return exact

def _paper_input_number(value,low,high):
    return float(_paper_input_decimal(value,low,high))

def paper_input_numeric_integrity(kind,payload):
    """Numeric-only v2 input predicate; no source, clock or availability grant.

    Domains precede legacy binary64 isclose(rel=abs=1e-9). Signed zero is
    numeric zero; negative tiny unsigned strings refuse before float underflow.
    Present-null funding is valid unknown data, never known funding proof.
    """
    if type(kind) is not str or type(payload) is not dict or len(payload)>64:return False
    bound=Decimal('1e15');minimum=Decimal('1e-15')
    try:
        if kind=='trade_tape_250ms':
            fields=('open','high','low','close','buy_volume','sell_volume','delta','cvd','range','aggressor_imbalance')
            values={key:_paper_input_number(payload[key],bound.copy_negate(),bound) for key in fields}
            for key in ('open','high','low','close'):
                _paper_input_number(payload[key],Decimal(0),bound)
                if values[key]<=0:return False
            for key in ('buy_volume','sell_volume','range'):_paper_input_number(payload[key],Decimal(0),bound)
            _paper_input_number(payload['aggressor_imbalance'],Decimal(-1),Decimal(1))
            counts=[payload[key] for key in ('buy_count','sell_count','trade_count')]
            if any(type(v) is not int or not 0<=v<=2**53-1 for v in counts) or counts[2]<1 or counts[0]+counts[1]!=counts[2]:return False
            prices=[_paper_input_decimal(payload[key],Decimal(0),bound) for key in ('open','high','low','close')]
            eo,eh,el,ec=prices
            if not el<=min(eo,ec)<=max(eo,ec)<=eh:return False
            o,h,l,cl=(values[k] for k in ('open','high','low','close'));buy=values['buy_volume'];sell=values['sell_volume'];total=buy+sell
            if not l<=min(o,cl)<=max(o,cl)<=h or total<=0:return False
            return all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9) for a,b in ((values['delta'],buy-sell),(values['range'],h-l),(values['aggressor_imbalance'],(buy-sell)/total)))
        if kind=='orderbook_snapshot':
            bid=_paper_input_decimal(payload['best_bid'],minimum,bound);ask=_paper_input_decimal(payload['best_ask'],minimum,bound)
            return bid<ask
        if kind=='derivatives_ticker':
            fields=('funding_rate','funding_interval_hour','next_funding_time')
            if not any(key in payload for key in fields):return False
            for key in fields:
                if key in payload and payload[key] is not None:_paper_input_number(payload[key],Decimal(-1) if key=='funding_rate' else minimum,Decimal(1) if key=='funding_rate' else Decimal('253402300799999'))
            return True
        return False
    except (KeyError,ValueError,TypeError,OverflowError,InvalidOperation):return False


def paper_quote_book_valid(bid,ask):
    """Pure quote-domain predicate: exact Decimal1e-12..1e12, bid<=ask.

    Locked books are allowed by causal paper quote policy. This deliberately
    differs from the Data input BOOK policy's stricter spread/different bounds.
    No source validity, freshness, execution or state authority is granted.
    """
    try:
        for value in (bid,ask):_causal_decimal(value,Decimal('1e-12'),Decimal('1e12'))
    except ValueError:return False
    return bid<=ask


def paper_quote_funding_valid(mark,rate):
    """Pure funding-row domain; selection/clocks/completeness stay external.

    Validate every supplied row before controller state changes, including rows
    outside a selected holding interval. Finite exact Decimal mark1e-12..1e12,
    rate-1..1; no rounding, schedule inference or source/execution authority.
    """
    try:
        _causal_decimal(mark,Decimal('1e-12'),Decimal('1e12'))
        _causal_decimal(rate,Decimal(-1),Decimal(1))
    except ValueError:return False
    return True


def rank_volatile_symbols(rows, *, min_turnover=Decimal('1000000')):
    """Full-universe exact volatility ranking; no age/status/count selection.

    Source Meta b1a4 exchange.top_volatile: abs(last/prev-1), descending
    (score, turnover, symbol). Rational comparison removes ambient rounding.
    Version2 refuses an entire malformed/duplicate refresh instead of silently
    skipping malformed rows. Valid nonpositive prices/subthreshold turnovers
    remain ineligible. Exact list/tuple<=4096 and closed four-field exact dicts;
    ASCII uppercase alphanumeric USDT symbols2..30 chars; Decimal or decimal
    string numbers<=256 chars,128 coefficient digits, exponent +/-4096.
    min_turnover is exact nonnegative Decimal. No source/execution authority.
    """
    from fractions import Fraction
    import re
    def number(value):
        if type(value) is str:
            if not 1<=len(value)<=256 or re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value) is None:
                raise ValueError('INVALID_RANKING_NUMBER')
            try:value=Decimal(value,context=Context())
            except InvalidOperation as exc:raise ValueError('INVALID_RANKING_NUMBER') from exc
        if type(value) is not Decimal or not value.is_finite():raise ValueError('INVALID_RANKING_NUMBER')
        parts=value.as_tuple()
        if len(parts.digits)>128 or not -4096<=parts.exponent<=4096:raise ValueError('RANKING_NUMBER_DOMAIN')
        return value
    if type(min_turnover) is not Decimal:raise ValueError('RANKING_MINIMUM_DECIMAL_REQUIRED')
    minimum=number(min_turnover)
    if minimum<0:raise ValueError('NEGATIVE_RANKING_MINIMUM')
    if type(rows) not in (list,tuple) or len(rows)>4096:raise ValueError('RANKING_ROWS_DOMAIN')
    fields=('symbol','turnover24h','lastPrice','prevPrice24h');seen=set();ranked=[]
    for row in rows:
        if type(row) is not dict or len(row)!=4:raise ValueError('RANKING_ROW_FIELDS')
        if any(type(key) is not str or key not in fields for key in row):raise ValueError('RANKING_ROW_FIELDS')
        symbol=row['symbol']
        if type(symbol) is not str or not 2<=len(symbol)<=30 or (re.fullmatch(r'[A-Z0-9]+',symbol) is None or not symbol.endswith('USDT')):raise ValueError('RANKING_SYMBOL_DOMAIN')
        if symbol in seen:raise ValueError('DUPLICATE_RANKING_SYMBOL')
        seen.add(symbol)
        turnover,last,previous=(number(row[key]) for key in fields[1:])
        if turnover<minimum or last<=0 or previous<=0:continue
        score=abs(Fraction(last)/Fraction(previous)-1)
        ranked.append((score,turnover,symbol))
    ranked.sort(reverse=True)
    return tuple(symbol for score,turnover,symbol in ranked)


def exact_scaled_integer(value,scale):
    """Exact bounded unit conversion, never rounding/flooring a fraction.

    Exact finite Decimal,<=128 coefficient digits, exponent +/-1000;
    literal int scale1..86400000; exact integral result0..2**53-1.
    Numeric signed zero is zero. Source/time/positivity policy stays external.
    No caller precision, traps or flags participate in integer arithmetic.
    """
    if type(scale) is not int or not 1<=scale<=86400000:raise ValueError('EXACT_INTEGER_SCALE_DOMAIN')
    _causal_decimal(value,Decimal(0),Decimal(2**53-1))
    numerator,denominator=value.as_integer_ratio()
    result,remainder=divmod(numerator*scale,denominator)
    if remainder or not 0<=result<=2**53-1:raise ValueError('EXACT_SCALED_INTEGER_REQUIRED')
    return result


def history_window_ms(start_ms,end_ms,*,cadence_minutes):
    """Inclusive UTC-ms sampling grid, without metadata/readiness authority.

    Exact nonbool ints: times0..253402300799999, cadence1..2**53-1 minutes.
    Bounds are representation budgets, not provider/exchange cadence policy.
    Return ceil(start)/floor(end) grid points or None for an empty/reversed
    interval; an aligned singleton (including epoch0) remains nonempty.
    Integer-only arithmetic leaves every Decimal context/trap/flag untouched.
    """
    maximum=253402300799999
    if type(start_ms) is not int or type(end_ms) is not int or not 0<=start_ms<=maximum or not 0<=end_ms<=maximum:
        raise ValueError('HISTORY_WINDOW_UTC_MS_DOMAIN')
    if type(cadence_minutes) is not int or not 1<=cadence_minutes<=2**53-1:
        raise ValueError('HISTORY_WINDOW_CADENCE_DOMAIN')
    if end_ms<start_ms:return None
    step=cadence_minutes*60000
    first=((start_ms+step-1)//step)*step
    last=(end_ms//step)*step
    return (first,last) if first<=last else None


def candle_ohlcv_turnover_valid(open,high,low,close,volume,*,turnover):
    """Six-field Decimal domain predicate using the shared OHLCV predicate.

    Turnover is required, finite, nonnegative and bounded by the same128digit
    coefficient/exponent+/-4096 policy. No source/coverage/trade grant is made.
    Existing five-field consumers retain their distinct still-active contract.
    """
    if not candle_ohlcv_valid(open,high,low,close,volume):return False
    try:_policy_decimal(turnover,nonnegative=True)
    except ValueError:return False
    return True


def query_minute_grid_ms(start_ms,end_ms,*,event_cut_ms=None):
    """Bounded half-open whole-minute cells for a declared synthetic query.

    Reuse the inclusive history kernel's literal UTC domain. This stricter
    request rejects empty/reversed/off-grid intervals; at most1440 cells is a
    query resource budget, never an exchange coverage or readiness statement.
    Optional cut need not be aligned, but must be a literal UTC int>=end.
    No source, capability, event availability or trading authority is assigned.
    """
    window=history_window_ms(start_ms,end_ms,cadence_minutes=1)
    if window is None or start_ms>=end_ms or window!=(start_ms,end_ms):
        raise ValueError('QUERY_WHOLE_MINUTE_RANGE_REQUIRED')
    if (end_ms-start_ms)//60000>1440:raise ValueError('QUERY_MINUTE_CELL_BUDGET')
    if event_cut_ms is not None and history_window_ms(end_ms,event_cut_ms,cadence_minutes=1) is None:
        raise ValueError('QUERY_EVENT_CUT_PRECEDES_END')
    return tuple((point,point+60000) for point in range(start_ms,end_ms,60000))


def percent_to_fraction(value):
    """Exact bounded Decimal percent -> fraction, with no rounding or policy.

    Strict finite Decimal, <=128coefficient digits and exponent+/-4096.
    The output shifts the decimal quantum by-2 (exponent-4098..4094), preserving
    coefficient and signed zero. Values outside0..100 remain legitimate numeric
    percentages; caller-owned fee/threshold/risk policy is checked separately.
    No caller precision, traps or flags participate in this unit conversion.
    """
    _policy_decimal(value)
    sign,digits,exponent=value.as_tuple()
    return Decimal((sign,digits,exponent-2))


def finite_nonnegative_number_valid(value):
    """Literal int/float finite-binary64 nonnegative predicate, no policy grant.

    Boolean/subclass/string/Decimal coercion is refused. Reuse the existing
    bounded conversion (int bit length<=1024, finite binary64) so oversized
    integers refuse before unbounded conversion and overflow never escapes.
    Signed zero is nonnegative; caller Decimal contexts remain untouched.
    This validates legacy JSON numeric shape, not financial exactness, source
    authenticity, fee/risk policy, or permission to execute any operation.
    """
    if type(value) is not int and type(value) is not float:return False
    try:return _paper_binary64(value)>=0
    except ValueError:return False


def causal_volatility_metrics(candles,*,window=20,percentile_lookback=252,bar_duration_ms):
    """Bounded causal binary64 volatility metrics; no data IO or strategy policy.

    Original Strattester volatility formulas: mean true range / close,
    RMS log return, Parkinson, current-window range, prior-window volume and
    turnover ratios, and percentile against prior ATR observations only.
    Strict canonical eight-field OHLCV rows; timestamp units are explicit ms.
    available_at_ms is a required CALLER_DECLARED clock, never authenticated
    availability/PIT evidence. It must not precede the bar end. Output uses the
    maximum declared clock over the entire consumed prefix (including prior
    close and ATR percentile dependencies); no bar-close default is inferred.
    Output tuples contain start, available, seven metrics and regime index0..4.
    Budgets are representation/work limits, never coverage/source authority.
    """
    from statistics import mean
    if (type(window) is not int or not 2<=window<=4096
            or type(percentile_lookback) is not int or not 1<=percentile_lookback<=4096
            or type(bar_duration_ms) is not int or not 1<=bar_duration_ms<=253402300799999):
        raise ValueError('VOLATILITY_PARAMETER_DOMAIN')
    if (type(candles) is not list and type(candles) is not tuple) or len(candles)>4096:
        raise ValueError('VOLATILITY_ROW_BUDGET')
    if len(candles)*(window+percentile_lookback)>2_000_000:raise ValueError('VOLATILITY_WORK_BUDGET')
    fields=('event_start_ms','open','high','low','close','volume','turnover','available_at_ms');rows=[];previous=None;availability=[]
    for row in candles:
        if type(row) is not dict or len(row)!=8 or any(type(key) is not str or key not in fields for key in row):
            raise ValueError('VOLATILITY_ROW_FIELDS')
        start=row['event_start_ms']
        if (type(start) is not int or not 0<=start<=253402300799999-bar_duration_ms
                or previous is not None and start<previous+bar_duration_ms):raise ValueError('VOLATILITY_TIME_DOMAIN')
        available=row['available_at_ms']
        if type(available) is not int or not start+bar_duration_ms<=available<=253402300799999:
            raise ValueError('VOLATILITY_AVAILABILITY_DOMAIN')
        availability.append(available)
        values=[]
        for field in fields[1:7]:
            value=row[field]
            if type(value) is not int and type(value) is not float:raise ValueError('VOLATILITY_LITERAL_NUMBER_REQUIRED')
            number=_paper_binary64(value)
            if type(value) is int and int(number)!=value:raise ValueError('VOLATILITY_INTEGER_NOT_EXACT_BINARY64')
            if number<0 or field not in ('volume','turnover') and number==0:raise ValueError('VOLATILITY_NUMBER_DOMAIN')
            values.append(number)
        open_,high,low,close,volume,turnover=values
        if not low<=open_<=high or not low<=close<=high:raise ValueError('VOLATILITY_OHLC_DOMAIN')
        rows.append((start,open_,high,low,close,volume,turnover));previous=start
    rows=tuple(rows)
    if len(rows)<window:return ()
    atr_history=[];true_ranges=[];log_returns=[];park_terms=[];out=[];prefix_available=0
    try:
        for index,(stamp,open_,high,low,close,volume,turnover) in enumerate(rows):
            prefix_available=max(prefix_available,availability[index])
            prev_close=rows[index-1][4] if index else open_
            true_ranges.append(max(high-low,abs(high-prev_close),abs(low-prev_close)))
            log_returns.append(math.log(close/prev_close) if index else 0.0)
            park_terms.append(math.log(high/low)**2)
            if index+1<window:continue
            lower=index+1-window;selected=rows[lower:index+1]
            atr_fraction=mean(true_ranges[lower:index+1])/close
            rets=log_returns[lower:index+1];realized=math.sqrt(sum(value*value for value in rets)/len(rets))
            terms=park_terms[lower:index+1];parkinson=math.sqrt(sum(terms)/(4*math.log(2)*len(terms)))
            range_fraction=(max(row[2] for row in selected)-min(row[3] for row in selected))/close
            volume_base=mean(row[5] for row in selected[:-1]);turnover_base=mean(row[6] for row in selected[:-1])
            volume_ratio=volume/volume_base if volume_base>0 else 1.0
            turnover_ratio=turnover/turnover_base if turnover_base>0 else 1.0
            prior=atr_history[-percentile_lookback:]
            percentile=sum(value<=atr_fraction for value in prior)/len(prior) if prior else .5
            metrics=tuple(_paper_binary64(value) for value in (atr_fraction,realized,parkinson,range_fraction,volume_ratio,turnover_ratio,percentile))
            regime=0 if percentile<=.20 else 1 if percentile<=.40 else 2 if percentile<=.60 else 3 if percentile<=.80 else 4
            out.append((stamp,prefix_available,*metrics,regime));atr_history.append(atr_fraction)
    except (ValueError,OverflowError,ZeroDivisionError) as exc:raise ValueError('VOLATILITY_DERIVED_DOMAIN') from exc
    return tuple(out)


# Binary64 scientific value-area transfer. Existing Decimal profile arithmetic
# remains canonical; only POC comparison reuses it after legacy float accumulation.
from typing import NamedTuple as _ValueAreaNamedTuple

class ValueAreaMetrics(_ValueAreaNamedTuple):
    poc: int | float
    value_area_high: int | float
    value_area_low: int | float
    value_area_width: int | float
    decision_ms: int
    available_at_ms: int
    basis: str

def _value_area_clock(value):
    if type(value) is not int or not 0<=value<=253402300799999:
        raise ValueError('VALUE_AREA_LITERAL_UTC_MS_REQUIRED')
    return value

def _value_area_number(value,*,positive=False):
    if type(value) is not int and type(value) is not float:
        raise ValueError('VALUE_AREA_LITERAL_BINARY64_REQUIRED')
    if not finite_nonnegative_number_valid(value):
        raise ValueError('VALUE_AREA_NUMBER_DOMAIN')
    number=_paper_binary64(value)
    if type(value) is int and int(number)!=value:
        raise ValueError('VALUE_AREA_INTEGER_NOT_EXACT_BINARY64')
    if positive and number==0:raise ValueError('VALUE_AREA_POSITIVE_PRICE_REQUIRED')
    # Preserve the original literal key/arithmetic type. In particular, integer
    # price keys and all-integer typical-price addition must not round early.
    return value

def _value_area_points(rows,*,candles):
    if (type(rows) is not list and type(rows) is not tuple) or len(rows)>4096:
        raise ValueError('VALUE_AREA_ROW_BUDGET')
    fields=(('event_start_ms','event_end_ms','available_at_ms','high','low','close','volume')
            if candles else ('event_ms','available_at_ms','price','volume'))
    snapshot=tuple(rows);out=[]
    for row in snapshot:
        if (type(row) is not dict or len(row)!=len(fields)
                or any(type(key) is not str or key not in fields for key in row)):
            raise ValueError('VALUE_AREA_CLOSED_FIELDS_REQUIRED')
        values=tuple(row[key] for key in fields)
        if candles:
            start,end,available,high,low,close,volume=values
            _value_area_clock(start);_value_area_clock(end);_value_area_clock(available)
            if not start<end<=available:raise ValueError('VALUE_AREA_CANDLE_CLOCK_ORDER')
            for number in (high,low,close):_value_area_number(number,positive=True)
            _value_area_number(volume)
            if not low<=close<=high:raise ValueError('VALUE_AREA_CANDLE_PRICE_ORDER')
            try:price=(high+low+close)/3
            except (OverflowError,ValueError,ZeroDivisionError):
                raise ValueError('VALUE_AREA_TYPICAL_PRICE_DOMAIN') from None
            _value_area_number(price,positive=True)
            out.append((start,available,price,volume))
        else:
            event,available,price,volume=values
            _value_area_clock(event);_value_area_clock(available)
            if available<event:raise ValueError('VALUE_AREA_TRADE_CLOCK_ORDER')
            _value_area_number(price,positive=True);_value_area_number(volume)
            out.append((event,available,price,volume))
    return tuple(out)

def _value_area_bins(points):
    """One binary64 accumulation routine, also preflighting future-only totals."""
    volume={}
    try:
        for _,_,price,quantity in points:
            combined=volume.get(price,0.0)+quantity
            if not finite_nonnegative_number_valid(combined):
                raise ValueError('VALUE_AREA_AGGREGATE_DOMAIN')
            volume[price]=combined
        total=sum(volume.values())
        if not finite_nonnegative_number_valid(total):
            raise ValueError('VALUE_AREA_TOTAL_DOMAIN')
    except (OverflowError,ValueError):
        raise ValueError('VALUE_AREA_DERIVED_DOMAIN') from None
    return volume,total

def _value_area_metrics(rows,*,decision_ms,candles):
    decision=_value_area_clock(decision_ms)
    points=_value_area_points(rows,candles=candles)
    # A closed input batch must be numerically valid even when its later rows
    # are not yet eligible. No malformed future row or aggregate is ignored.
    all_bins,all_total=_value_area_bins(points)
    eligible=tuple(point for point in points if point[0]<=decision and point[1]<=decision)
    if not eligible:raise ValueError('VALUE_AREA_NO_ELIGIBLE_OBSERVATIONS')
    volume,total=(all_bins,all_total) if len(eligible)==len(points) else _value_area_bins(eligible)
    # str of each admitted finite binary64 value round-trips and preserves its
    # total ordering. Exact-binary64 integer input keys lie on that same grid.
    # Thus this comparison-only Decimal projection preserves volume/price ties.
    # It does NOT change accumulation, target, ranked ties or typical arithmetic.
    compared={};original={}
    for price,quantity in volume.items():
        key=Decimal(str(price))
        if key in compared:raise ValueError('VALUE_AREA_POC_KEY_COLLISION')
        compared[key]=Decimal(str(quantity));original[key]=price
    poc=original[volume_profile_poc(compared)]
    target=total*.70;accumulated=0;selected=[]
    for price in sorted(volume,key=volume.get,reverse=True):
        selected.append(price);accumulated+=volume[price]
        if not finite_nonnegative_number_valid(accumulated):
            raise ValueError('VALUE_AREA_DERIVED_DOMAIN')
        if accumulated>=target:break
    low=min(selected);high=max(selected);width=high-low
    _value_area_number(width)
    return ValueAreaMetrics(poc,high,low,width,decision,max(point[1] for point in eligible),
                            'CANDLE_TYPICAL_PRICE_PROXY' if candles else 'EXECUTED_TRADE_PRICE_BINS')

def trade_value_area_metrics(rows,*,decision_ms):
    """Frozen causal scientific trade bins; no source, coverage or trade grant.

    Closed rows require event_ms, available_at_ms, price and volume. Both clocks
    are explicit literal UTC milliseconds; availability may never precede event.
    At most4096 rows, finite nonnegative literal int/float values, positive
    prices and exactly representable integer inputs. All rows and all-row totals
    are preflighted, including future rows. Eligible order/insertion is retained.
    Lowest-price POC ties reuse the Decimal POC selector after binary64 sums.
    Ranked70% value area intentionally uses stable first-seen ties, as the
    original scientific model did; it need not contain a tied lowest-price POC.
    decision_ms is a request cutoff, not an inferred availability observation.
    available_at_ms is the max caller-declared clock actually consumed.
    """
    return _value_area_metrics(rows,decision_ms=decision_ms,candles=False)

def candle_proxy_value_area_metrics(rows,*,decision_ms):
    """Frozen candle-typical-price approximation; never trade-price distribution.

    Closed rows require event_start_ms,event_end_ms,available_at_ms,high,low,
    close,volume. End>start and availability>=end must be declared explicitly.
    No bar duration, end, close clock or source availability is reconstructed.
    Uses exactly the original native (high+low+close)/3 expression, float volume
    accumulation and stable ranked70% policy, with the trade kernel's strict
    bounds/refusal rules. This numeric record is not source authentication.
    """
    return _value_area_metrics(rows,decision_ms=decision_ms,candles=True)


def lossless_nonnegative_binary64_valid(value):
    """Literal finite nonnegative int/float with exact integer roundtrip.

    Reuse the profile numerical-domain core. This stricter predicate leaves
    finite_nonnegative_number_valid's existing legacy JSON-shape policy intact.
    Booleans, subclasses, strings and Decimal values are not converted; huge
    integers refuse through the same bounded binary64 conversion. No financial,
    source, execution or availability policy is granted by a true result.
    """
    try:_value_area_number(value)
    except ValueError:return False
    return True


class ResearchBracketPrices(NamedTuple):
    stop_loss: float
    take_profit: float

    def as_decimal(self):
        """Decimal presentation of finite binary64 thresholds, not price admission.

        Uses each float's shortest decimal spelling, preserving signed results.
        No precision recovery, rounding policy, context mutation or executable
        order validation is implied. Fabricated/subclass records refuse before
        foreign conversion callbacks can run.
        """
        if type(self) is not ResearchBracketPrices:
            raise ValueError('RESEARCH_BRACKET_LITERAL_RECORD_REQUIRED')
        if (type(self.stop_loss) is not float or type(self.take_profit) is not float
                or not isfinite(self.stop_loss) or not isfinite(self.take_profit)):
            raise ValueError('RESEARCH_BRACKET_FINITE_FLOAT_FIELDS_REQUIRED')
        return Decimal(str(self.stop_loss)),Decimal(str(self.take_profit))


def research_bracket_prices(entry_price,atr_fraction,side,*,reward_risk=1.5,stop_atr=.75):
    """Pure legacy binary64 research geometry, never executable order admission.

    Preserves Data research's exact multiplication/max/addition order and its
    minimum0.0005 entry fraction. Inputs are literal, finite, nonnegative and
    lossless in binary64; entry must be positive. Signed algebraic output
    thresholds are retained, including stops/targets below zero. A caller must
    separately admit execution prices, ticks, risk, data clocks and authority.
    No rounding, coercive strings, IO, simulation state or permission is added.
    """
    if type(side) is not str or side not in ('long','short'):
        raise ValueError('RESEARCH_BRACKET_SIDE_REQUIRED')
    for value in (entry_price,atr_fraction,reward_risk,stop_atr):
        if not lossless_nonnegative_binary64_valid(value):
            raise ValueError('RESEARCH_BRACKET_NUMBER_DOMAIN')
    if entry_price==0:raise ValueError('RESEARCH_BRACKET_POSITIVE_ENTRY_REQUIRED')
    entry=_paper_binary64(entry_price);atr=_paper_binary64(atr_fraction)
    reward=_paper_binary64(reward_risk);multiplier=_paper_binary64(stop_atr)
    distance=max(entry*max(atr,.0005)*multiplier,entry*.0005)
    stop=entry-distance if side=='long' else entry+distance
    target=entry+distance*reward if side=='long' else entry-distance*reward
    return ResearchBracketPrices(_paper_binary64(stop),_paper_binary64(target))


def research_expansion_side(open_price,close_price,atr_fraction,*,min_body_atr=.5):
    """Original binary64 candle-body threshold; direction policy, not an order.

    No availability is inferred. Equality passes the original threshold; a zero
    body with zero threshold retains its original short-side classification.
    Callers provide separately validated clocks and research observations.
    """
    for value in (open_price,close_price,atr_fraction,min_body_atr):
        if not lossless_nonnegative_binary64_valid(value):
            raise ValueError('RESEARCH_BODY_NUMBER_DOMAIN')
    if open_price==0 or close_price==0:
        raise ValueError('RESEARCH_BODY_POSITIVE_PRICE_REQUIRED')
    opening=_paper_binary64(open_price);closing=_paper_binary64(close_price)
    atr=_paper_binary64(atr_fraction);minimum=_paper_binary64(min_body_atr)
    body=_paper_binary64(closing-opening)
    threshold=_paper_binary64(closing*atr*minimum)
    if abs(body)<threshold:return None
    return 'long' if body>0 else 'short'


class PriceStructurePattern(NamedTuple):
    index: int
    kind: int
    low: int|float
    high: int|float
    dependency_start: int
    dependency_stop: int


def price_structure_patterns(ranges,*,left=2,right=2):
    """Pure strict swing and three-range gap comparisons from research SMC.

    Closed literal rows are (high,low), at most4096. Codes0/1 are strict
    high/low swings and2/3 upward/downward gaps. Each immutable result includes
    its complete half-open dependency-index interval so an analysis owner can
    bind actual declared availability without inferring clocks. Original numeric
    values and strict tie behavior are preserved. Zero is allowed as geometry,
    not executable-price admission. No trend, strategy, IO or trust is assigned.
    """
    if (type(left) is not int or type(right) is not int
            or not 1<=left<=64 or not 1<=right<=64):
        raise ValueError('PRICE_STRUCTURE_LITERAL_WINDOW_REQUIRED')
    if (type(ranges) is not tuple and type(ranges) is not list) or len(ranges)>4096:
        raise ValueError('PRICE_STRUCTURE_BOUNDED_LITERAL_ROWS_REQUIRED')
    rows=[]
    for row in tuple(ranges):
        if (type(row) is not tuple and type(row) is not list) or len(row)!=2:
            raise ValueError('PRICE_STRUCTURE_CLOSED_RANGE_REQUIRED')
        high,low=row
        _value_area_number(high);_value_area_number(low)
        if low>high:raise ValueError('PRICE_STRUCTURE_ORDERED_RANGE_REQUIRED')
        rows.append((high,low))
    out=[]
    for index in range(left,len(rows)-right):
        high,low=rows[index]
        neighbors=rows[index-left:index]+rows[index+1:index+1+right]
        if all(high>row[0] for row in neighbors):
            out.append(PriceStructurePattern(index,0,high,high,index-left,index+right+1))
        if all(low<row[1] for row in neighbors):
            out.append(PriceStructurePattern(index,1,low,low,index-left,index+right+1))
    for index in range(2,len(rows)):
        prior_high,prior_low=rows[index-2];high,low=rows[index]
        if low>prior_high:
            out.append(PriceStructurePattern(index,2,prior_high,low,index-2,index+1))
        elif high<prior_low:
            out.append(PriceStructurePattern(index,3,high,prior_low,index-2,index+1))
    return tuple(sorted(out,key=lambda item:(item.index,item.kind)))


def lossless_binary64_valid(value):
    """Literal finite signed int/float with exact integer binary64 roundtrip.

    Reuse the nonnegative numerical-domain core; no string/Decimal/subclass
    coercion, foreign callbacks, financial policy or source authority is added.
    """
    if type(value) is int:
        if value.bit_length()>1024:return False
    elif type(value) is not float:return False
    return lossless_nonnegative_binary64_valid(-value if value<0 else value)


def research_retest_matches(high_price,low_price,close_price,reference_price,side,*,tolerance=.0015):
    """Original binary64 retest boundary comparisons, not executable admission.

    Literal finite lossless positive ordered prices and nonnegative tolerance
    are required. Preserves reference*(1+tolerance)/(1-tolerance) order and
    inclusive wick touch with a strict closing cross. Finite algebraic negative
    short thresholds remain geometry; nonrepresentable boundaries refuse.
    """
    if type(side) is not str or side not in ('long','short'):
        raise ValueError('RESEARCH_RETEST_LITERAL_SIDE_REQUIRED')
    for value in (high_price,low_price,close_price,reference_price):
        _value_area_number(value,positive=True)
    _value_area_number(tolerance)
    if not low_price<=close_price<=high_price:
        raise ValueError('RESEARCH_RETEST_ORDERED_PRICES_REQUIRED')
    high,low,close,reference,margin=map(_paper_binary64,(high_price,low_price,close_price,reference_price,tolerance))
    boundary=_paper_binary64(reference*(1+margin if side=='long' else 1-margin))
    return (low<=boundary and close>reference) if side=='long' else (high>=boundary and close<reference)


def executed_notional_consistent(turnover, volume):
    """Only finite nonnegative zero/nonzero consistency, never quantity proof.

    Accept either literal int/float binary64-domain values (the existing lossless
    nonnegative predicate) or two plain finite Decimal presentation values.
    Decimal and binary64 presentations cannot mix. No conversion, callbacks,
    arithmetic, OHLC bounds, source authentication or quote-quantity proof is
    inferred. Decimal comparisons preserve caller context flags and traps.
    """
    if type(turnover) is Decimal and type(volume) is Decimal:
        if not turnover.is_finite() or not volume.is_finite():
            return False
        if turnover < 0 or volume < 0:
            return False
    elif (type(turnover) is int or type(turnover) is float) and (type(volume) is int or type(volume) is float):
        if not lossless_nonnegative_binary64_valid(turnover) or not lossless_nonnegative_binary64_valid(volume):
            return False
    else:
        return False
    return (turnover == 0) == (volume == 0)

def paper_execution_values_valid(entry, exit, quantity, fees):
    """Validate caller-declared execution values in the Paper Decimal domain.

    Prices and quantity are strictly positive; aggregate fees are nonnegative.
    Exact plain finite Decimal values only, <=128 coefficient digits and an
    exponent within +/-4096. No arithmetic, PnL, units, fill, source or authority
    inference is performed. Invalid declarations return a literal False without
    coercion or dependence on the caller's Decimal context.
    """
    try:
        for value in (entry, exit, quantity):
            _policy_decimal(value, positive=True)
        _policy_decimal(fees, nonnegative=True)
    except ValueError:
        return False
    return True


# PAPER_SCALE_ACCOUNTING_V1: caller-declared chronological pooled-cost model.
class PaperScaleEntryMetrics(NamedTuple):
    price: Decimal
    quantity: Decimal

class PaperScaleEvent(NamedTuple):
    kind: str
    price: Decimal
    quantity: Decimal

class PaperScaleState(NamedTuple):
    remaining_quantity: Decimal
    remaining_cost: Decimal
    current_entry_price: Decimal | None
    opened_quantity: Decimal
    exited_quantity: Decimal
    entry_value_total: Decimal
    exit_value_total: Decimal
    entry_mean: Decimal | None
    exit_mean: Decimal | None
    gross_pnl: Decimal
    entry_fees: Decimal
    exit_fees: Decimal
    fees: Decimal
    net_pnl: Decimal
    closed: bool

def _scale_amount(value, *, positive=False, nonnegative=False):
    # Exact type admission precedes the existing accumulated-amount policy.
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError('SCALE_PLAIN_FINITE_DECIMAL_REQUIRED')
    _market_amount(value)
    if positive and value<=0 or nonnegative and value<0:
        raise ValueError('SCALE_AMOUNT_SIGN')
    return value

def _scale_fraction(value):
    _policy_decimal(value,positive=True)
    _scale_amount(value,positive=True)
    if value>1:raise ValueError('SCALE_FRACTION_DOMAIN')
    return value

def paper_scale_fractions_valid(fractions):
    """Exact positive Decimal plan fractions, not approximate binary64 weights.

    Exact tuple of1..16 values, each <=128 digits/exponent +/-2000. All
    declarations are captured before arithmetic. Exact sum must equal one.
    No units, plan execution, source authenticity or authority is inferred.
    """
    if type(fractions) is not tuple or not 1<=len(fractions)<=16:return False
    captured=tuple(fractions)
    try:
        for value in captured:_scale_fraction(value)
        total=exact_sum(captured)
    except ValueError:return False
    return total==Decimal(1)

def paper_scale_entry_metrics(side,raw_entry,notional,fraction,slippage_bps):
    """Private28 allocation, adverse price and canonical position sizing.

    The old paper_scale_value binary64 API is intentionally not used. Quantity
    and allocated value additionally obey the existing exact-amount resource
    budget. Fees are charged separately on actual executed price*quantity.
    """
    side,raw_entry,notional,fraction,slippage_bps=(side,raw_entry,notional,fraction,slippage_bps)
    _paper_side(side);_policy_decimal(raw_entry,positive=True)
    _policy_decimal(notional,positive=True);_scale_amount(notional,positive=True)
    _scale_fraction(fraction);_policy_decimal(slippage_bps,nonnegative=True)
    if slippage_bps>=10000:raise ValueError('INVALID_PAPER_SLIPPAGE')
    allocated=_scale_amount(_paper_context().multiply(notional,fraction),positive=True)
    _policy_decimal(allocated,positive=True)
    price=adverse_execution_price(raw_entry,side,slippage_bps,True)
    quantity=_scale_amount(paper_position_size(allocated,price),positive=True)
    return PaperScaleEntryMetrics(price,quantity)

def paper_scale_target_quantity(remaining,opened,fraction):
    """Earlier targets use a fraction of opened quantity, capped by remaining.

    The caller passes fraction=1 for its final target or EOD closure; that path
    returns the exact entire remainder. A partial product rounded to the entire
    opened quantity refuses instead of erasing a positive nominal complement.
    """
    remaining,opened,fraction=(remaining,opened,fraction)
    _scale_amount(remaining,positive=True);_scale_amount(opened,positive=True)
    _scale_fraction(fraction)
    if remaining>opened:raise ValueError('SCALE_REMAINING_EXCEEDS_OPENED')
    if fraction==1:return remaining
    quantity=_scale_amount(_paper_context().multiply(opened,fraction),positive=True)
    if quantity>=opened:raise ValueError('SCALE_TARGET_ROUNDING_COLLAPSE')
    return min(remaining,quantity)

def _scale_basis_notional(price,quantity):
    # The basis pool uses exact products, separate from rounded fee/ledger values.
    # Existing fixed precision traps refuse products outside its exact resource
    # budget; no global summation or input policy is widened.
    try:value=_market_context().multiply(price,quantity)
    except Inexact as exc:raise ValueError('SCALE_EXACT_BASIS_BUDGET') from exc
    return _scale_amount(value,positive=True)

def paper_scale_accounting(side,events,fee_rate):
    """PAPER_SCALE_ACCOUNTING_V1; no scheduling, simulation or market inference.

    Snapshot all exact typed event leaves before any financial helper. Up to64
    ENTRY/EXIT records; raw prices use Paper128 digits/exponent +/-4096. Exact
    quantity/cost/totals use existing4270 digits/exponent +/-2000/adjusted<=2262
    resource policy. All derived violations refuse atomically. Per-event values
    and fees use explicit sequential28 rounding; their totals and conservation
    are exact within that budget, not recovered unrounded accounting.

    Partial exits allocate the smaller quantity side with a28-digit cost share;
    the other cost side is the exact complement. Full closure releases every
    remaining cost unit. Later entries never rebase a previous realization.
    The current execution-entry basis is unchanged on partial exits. A later
    entry weights the prior basis and new price by their exact remaining/new
    quantities, then divides in private28 arithmetic. It is separate from the
    rounded ledger cost ratio, which may contain allocation dust.
    Open-state net includes charged fees and realized gross, no unrealized mark.
    """
    if (type(events) is not tuple and type(events) is not list) or len(events)>64:
        raise ValueError('SCALE_BOUNDED_LITERAL_EVENTS_REQUIRED')
    captured=tuple(events)
    for event in captured:
        if type(event) is not PaperScaleEvent:raise ValueError('SCALE_EXACT_EVENT_REQUIRED')
    captured=tuple(tuple(event) for event in captured)
    _paper_side(side);_policy_decimal(fee_rate,nonnegative=True)
    _scale_amount(fee_rate,nonnegative=True)
    if fee_rate>=1:raise ValueError('INVALID_PAPER_FEE')
    for kind,price,quantity in captured:
        if type(kind) is not str or kind not in ('ENTRY','EXIT'):
            raise ValueError('SCALE_CLOSED_EVENT_KIND_REQUIRED')
        _policy_decimal(price,positive=True);_scale_amount(quantity,positive=True)
    c=_paper_context();zero=Decimal(0)
    remaining=cost=zero;basis=None;closed=False
    entry_quantities=[];exit_quantities=[];entry_values=[];exit_values=[]
    entry_fees=[];exit_fees=[];realized=[]
    for kind,price,quantity in captured:
        if closed:raise ValueError('SCALE_EVENT_AFTER_TERMINAL_CLOSE')
        if kind=='EXIT' and (remaining<=0 or quantity>remaining):
            raise ValueError('SCALE_EXIT_EXCEEDS_REMAINING')
        value=_scale_amount(c.multiply(price,quantity),positive=True)
        fee=_scale_amount(paper_entry_fee(value,fee_rate),nonnegative=True)
        if kind=='ENTRY':
            new_remaining=exact_sum((remaining,quantity))
            if remaining==0:basis=price
            else:
                basis_value=exact_sum((_scale_basis_notional(basis,remaining),
                                       _scale_basis_notional(price,quantity)))
                basis=_policy_decimal(c.divide(basis_value,new_remaining),positive=True)
            remaining=new_remaining;cost=exact_sum((cost,value))
            entry_quantities.append(quantity);entry_values.append(value);entry_fees.append(fee)
        else:
            after=exact_sum((remaining,quantity.copy_negate()))
            if quantity==remaining:
                released=cost;retained=zero;basis=None;closed=True
            else:
                exit_smaller=quantity<=after
                small_quantity=quantity if exit_smaller else after
                share=_policy_decimal(c.divide(small_quantity,remaining),positive=True)
                small_cost=_scale_amount(c.multiply(cost,share),positive=True)
                if small_cost>=cost:raise ValueError('SCALE_COST_ALLOCATION_COLLAPSE')
                complement=_scale_amount(exact_sum((cost,small_cost.copy_negate())),positive=True)
                released,retained=(small_cost,complement) if exit_smaller else (complement,small_cost)
            gross=exact_sum((value,released.copy_negate())) if side=='long' else exact_sum((released,value.copy_negate()))
            realized.append(gross);exit_quantities.append(quantity)
            exit_values.append(value);exit_fees.append(fee)
            remaining=after;cost=retained
    opened=exact_sum(entry_quantities);exited=exact_sum(exit_quantities)
    entry_total=exact_sum(entry_values);exit_total=exact_sum(exit_values)
    gross=exact_sum(realized);entry_fee=exact_sum(entry_fees);exit_fee=exact_sum(exit_fees)
    fees=exact_sum((entry_fee,exit_fee));net=exact_sum((gross,fees.copy_negate()))
    def mean(value,quantity):
        return _policy_decimal(c.divide(value,quantity),positive=True) if quantity>0 else None
    return PaperScaleState(remaining,cost,basis,opened,exited,
        entry_total,exit_total,mean(entry_total,opened),mean(exit_total,exited),
        gross,entry_fee,exit_fee,fees,net,closed)
