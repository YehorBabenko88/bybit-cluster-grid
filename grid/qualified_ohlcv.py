"""Descriptive Grid OHLCV 1m projection, deliberately NOT causal qualification.

ROUND 09 B local candidate. This module opens no connection, calls no Bybit API,
starts no HTTP listener, writes no data, performs no market calculations and
provides no trading or research authority. Its reader is an injected existing
read-only database function. Mounting is subject to a separate source-path permit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re

SCHEMA = "grid.ohlcv_1m.descriptive.v1"
MAX_MINUTES = 1000
MAX_DECIMAL_CHARS = 4300
MAX_RESPONSE_BYTES = 8_388_608
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_SYMBOL = re.compile(r"[A-Z0-9]{2,30}\\Z")
_SOURCE = re.compile(r"[A-Za-z0-9_./:-]{1,128}\\Z")

# The existing Grid migration 24 stores this table. Never silently substitute
# candles_1m: it has a different provenance and directional-volume contract.
READ_SQL = (
    "SELECT ts,open,high,low,close,volume,turnover,source "
    "FROM ohlcv_1m WHERE symbol=%s AND ts>=%s AND ts<%s "
    "ORDER BY ts ASC LIMIT %s"
)


class DescriptiveReadError(ValueError):
    """Request/row is invalid; no partial result may escape."""


def _require(ok, reason):
    if ok is not True:
        raise DescriptiveReadError(reason)


def _clock(value):
    _require(type(value) is int and 0 <= value <= 2**53 - 1, "CLOCK_REQUIRED")
    return value


def _date_from_ms(value):
    try:
        return _EPOCH + timedelta(milliseconds=value)
    except (OverflowError, ValueError) as exc:
        raise DescriptiveReadError("CLOCK_OUT_OF_RANGE") from exc


def _ms_from_date(value):
    _require(type(value) is datetime and value.tzinfo is not None,
             "ROW_UTC_TIMESTAMP_REQUIRED")
    utc = value.astimezone(timezone.utc)
    diff = utc - _EPOCH
    _require(diff.days >= 0 and diff.microseconds % 1000 == 0,
             "ROW_MILLISECOND_REQUIRED")
    return diff.days * 86_400_000 + diff.seconds * 1000 + diff.microseconds // 1000


def _exact_stored_decimal(value, nullable=False):
    if nullable and value is None:
        return None
    _require(type(value) is Decimal and value.is_finite(), "ROW_DECIMAL_REQUIRED")
    # Only formatting PostgreSQL NUMERIC; no OHLC/volume arithmetic in Grid.
    rendered = "0" if value.is_zero() else format(value, "f")
    _require(0 < len(rendered) <= MAX_DECIMAL_CHARS, "ROW_DECIMAL_BUDGET")
    return rendered


def _request(symbol, start_ms, end_ms, as_of_ms):
    _require(type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None,
             "SYMBOL_REQUIRED")
    start = _clock(start_ms)
    end = _clock(end_ms)
    cutoff = _clock(as_of_ms)
    _require(start % 60_000 == 0 and end % 60_000 == 0 and start < end,
             "MINUTE_ALIGNMENT_REQUIRED")
    expected = (end - start) // 60_000
    _require(1 <= expected <= MAX_MINUTES, "MINUTE_WINDOW_BUDGET")
    _require(end <= cutoff, "OPEN_OR_FUTURE_WINDOW")
    return start, end, cutoff, expected


def _gap_intervals(start_ms, end_ms, present):
    # Exact requested boundaries, never inferred from first/last returned row.
    gaps = []
    opened = None
    for minute in range(start_ms, end_ms, 60_000):
        if minute not in present:
            if opened is None:
                opened = minute
        elif opened is not None:
            gaps.append({"start_ms": opened, "end_ms": minute,
                         "missing_minutes": (minute - opened) // 60_000,
                         "reason": "MINUTE_NOT_STORED"})
            opened = None
    if opened is not None:
        gaps.append({"start_ms": opened, "end_ms": end_ms,
                     "missing_minutes": (end_ms - opened) // 60_000,
                     "reason": "MINUTE_NOT_STORED"})
    return gaps


def descriptive_snapshot(symbol, start_ms, end_ms, as_of_ms, *, reader):
    """Read a bounded historical interval from Grid's existing read-only sink.

    `reader(sql, params)` is the existing Grid read function, not a writer.
    Despite the path name, this result is ALWAYS non-authorizing: legacy
    ohlcv_1m lacks independently attested per-row receipt/availability time.
    """
    start, end, cutoff, expected = _request(symbol, start_ms, end_ms, as_of_ms)
    _require(callable(reader), "READ_ONLY_READER_REQUIRED")
    raw = reader(READ_SQL, (symbol, _date_from_ms(start), _date_from_ms(end),
                            expected + 1))
    _require(type(raw) in (list, tuple) and len(raw) <= expected,
             "ROW_COUNT_AMBIGUOUS")
    observed = []
    present = set()
    source_declarations = set()
    for row in raw:
        _require(type(row) in (tuple, list) and len(row) == 8, "ROW_SHAPE_REQUIRED")
        timestamp = _ms_from_date(row[0])
        _require(start <= timestamp < end and timestamp % 60_000 == 0,
                 "ROW_TIME_OUTSIDE_SELECTION")
        _require(timestamp not in present, "DUPLICATE_OR_REVISION_AMBIGUITY")
        present.add(timestamp)
        source = row[7]
        _require(type(source) is str and _SOURCE.fullmatch(source) is not None,
                 "SOURCE_DECLARATION_REQUIRED")
        source_declarations.add(source)
        candle = {"t": timestamp, "open": _exact_stored_decimal(row[1]),
                  "high": _exact_stored_decimal(row[2]),
                  "low": _exact_stored_decimal(row[3]),
                  "close": _exact_stored_decimal(row[4]),
                  "volume": _exact_stored_decimal(row[5]),
                  "turnover": _exact_stored_decimal(row[6], nullable=True),
                  "source_declared": source}
        observed.append(candle)
    _require(all(observed[i]["t"] < observed[i + 1]["t"]
                 for i in range(len(observed) - 1)), "ROW_ORDER_REQUIRED")
    gaps = _gap_intervals(start, end, present)
    missing = expected - len(observed)
    status = "UNAVAILABLE" if not observed else "GAP" if missing else "PARTIAL"
    reason = ("NO_STORED_MINUTES" if status == "UNAVAILABLE" else
              "INCOMPLETE_STORED_MINUTES" if status == "GAP" else
              "SOURCE_AVAILABILITY_NOT_ATTESTED")
    envelope = {
        "schema": SCHEMA, "read_only": True, "descriptive_only": True,
        "symbol": symbol, "timeframe": "1m",
        "selection": {"start_ms": start, "end_ms": end, "as_of_ms": cutoff,
                      "interval_semantics": "HALF_OPEN_UTC_MS"},
        "status": status, "reason": reason,
        "coverage": {"expected_minutes": expected, "observed_minutes": len(observed),
                     "missing_minutes": missing, "gaps": gaps,
                     "basis": "LOCAL_STORED_ROW_OBSERVATION_ONLY"},
        "provenance": {"dataset": "ohlcv_1m", "owner": "Grid",
                       "source_declarations": sorted(source_declarations),
                       "source_authenticity": "UNATTESTED",
                       "source_revision": None, "raw_frame_sha256": None,
                       "independent_receipt": None,
                       "exchange_completeness": "NOT_ATTESTED",
                       "storage_immutability": "NOT_ATTESTED",
                       "availability_at_decision": "UNATTESTED",
                       "clock_receipt": None,
                       "numerical_encoding": "POSTGRES_NUMERIC_FIXED_DECIMAL_STRING"},
        "execution_authority": False, "trading_authorized": False,
        "paper_admitted": False, "causal_research_admitted": False,
        "rows": observed,
    }
    # Local size bound; never emit a truncated result with a misleading count.
    import json
    try:
        size = len(json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise DescriptiveReadError("RESULT_LITERAL_INVALID") from exc
    _require(size <= MAX_RESPONSE_BYTES, "RESULT_BYTE_BUDGET")
    return envelope
