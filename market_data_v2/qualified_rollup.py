"""Bounded, non-authorizing 1m -> 5m/15m qualified historical OHLCV view.

This is an additive DTO projection over the existing canonical Grid v2 minute
qualifier, NOT another Bybit transport, SQL writer, Math SDK or Root admission.
Exchange completeness, storage immutability and source authenticity remain
unattested. Never emit READY/AVAILABLE, paper or trading permission.
"""
from market_data.provenance import digest, canonical
from market_data.numeric_dto import volume_total, volume_delta
from .qualified_read_contract import ProvenanceReadError

MINUTES = {"5m": 5, "15m": 15}
MAX_SOURCE_MINUTES = 75


def project_qualified_rollup(envelope, *, timeframe, limit, now_ms):
    """Reject all incomplete, misaligned, stale or mixed-source minute windows."""
    def need(ok, reason):
        if ok is not True:
            raise ProvenanceReadError(reason)

    need(type(timeframe) is str and timeframe in MINUTES, "ROLLUP_TIMEFRAME")
    need(type(now_ms) is int and 0 < now_ms < 2**63, "ROLLUP_CLOCK")
    need(type(limit) is int and 1 <= limit <= 5, "ROLLUP_LIMIT")
    need(type(envelope) is dict
         and envelope.get("schema") == "market_data.qualified-read-envelope.v1"
         and envelope.get("timeframe") == "1m"
         and envelope.get("producer") == "market_data"
         and envelope.get("record_integrity") == "VERIFIED"
         and envelope.get("status") == "PARTIAL"
         and envelope.get("reason") == "EXCHANGE_COMPLETENESS_UNATTESTED"
         and envelope.get("source_authenticity") == "NOT_INDEPENDENTLY_ATTESTED"
         and envelope.get("exchange_completeness") == "NOT_ATTESTED"
         and envelope.get("storage_immutability") == "NOT_ATTESTED"
         and envelope.get("execution_authority") is False
         and envelope.get("trading_authorized") is False
         and envelope.get("paper_admitted") is False
         and envelope.get("read_only") is True
         and envelope.get("immutable") is False,
         "ROLLUP_SOURCE_NOT_QUALIFIED")
    width = MINUTES[timeframe]
    expected = width * limit
    need(1 <= expected <= MAX_SOURCE_MINUTES, "ROLLUP_MINUTE_BUDGET")
    rows = envelope.get("rows")
    need(type(rows) is list and len(rows) == expected, "ROLLUP_INCOMPLETE")
    coverage = envelope.get("coverage")
    need(type(coverage) is dict and coverage == {
        "expected_minutes": expected, "observed_minutes": expected,
        "missing_minutes": 0}, "ROLLUP_COVERAGE")
    need(envelope.get("source_revision") is not None
         and envelope.get("producer_epoch") is not None,
         "ROLLUP_LINEAGE")
    # The original qualifier has already verified source record hashes,
    # mathematical integrity, absolute clocks, duplicate starts and freshness.
    # Reaffirm the parent hash and exact unmodified row provenance at this seam.
    need(digest(rows) == envelope.get("dataset_fingerprint"), "ROLLUP_PARENT_HASH")
    start = rows[0].get("start_ms")
    need(type(start) is int and start % (width * 60000) == 0,
         "ROLLUP_ALIGNMENT")
    need(type(rows[-1].get("end_ms")) is int
         and rows[-1]["end_ms"] < now_ms, "ROLLUP_CLOSED_BAR_REQUIRED")
    need(all(type(row) is dict
             and row.get("start_ms") == start + i * 60000
             and row.get("status") == "PARTIAL"
             and row.get("source_identity_verified") is True
             and row.get("source", {}).get("epoch") == envelope["producer_epoch"]
             and row.get("source", {}).get("source_revision") == envelope["source_revision"]
             and row.get("symbol") == envelope.get("symbol")
             and row.get("dataset_fingerprint") == digest({
                 k: v for k, v in row.items() if k != "dataset_fingerprint"})
             for i, row in enumerate(rows)), "ROLLUP_RECORD_LINEAGE")
    windows = []
    for i in range(0, expected, width):
        group = rows[i:i + width]
        # Reuse Grid's original Decimal-to-binary64 DTO adapter backed by
        # market_math exact_sum and executed_volume_delta; no second Math SDK.
        try:
            buy = volume_total(row["candle"]["buy_volume"] for row in group)
            sell = volume_total(row["candle"]["sell_volume"] for row in group)
            delta = volume_delta(buy, sell)
            trades = sum(row["candle"]["trade_count"] for row in group)
        except (ValueError, OverflowError, ArithmeticError) as exc:
            raise ProvenanceReadError("ROLLUP_NUMERIC_UNAVAILABLE") from exc
        need(type(trades) is int and 0 <= trades < 2**63, "ROLLUP_TRADES")
        candle = {
            "start_ms": group[0]["start_ms"],
            "end_ms": group[-1]["end_ms"],
            "open": group[0]["candle"]["open"],
            "high": max(row["candle"]["high"] for row in group),
            "low": min(row["candle"]["low"] for row in group),
            "close": group[-1]["candle"]["close"],
            "buy_volume": buy,
            "sell_volume": sell,
            "delta": delta,
            "trade_count": trades,
            "source_minute_fingerprints": [row["dataset_fingerprint"] for row in group],
        }
        windows.append(candle)
    result = {
        "schema": "market_data.qualified-rollup-envelope.v1",
        "api_version": {"major": 2, "minor": 0},
        "producer": "market_data", "symbol": envelope["symbol"],
        "timeframe": timeframe, "limit": limit,
        "status": "PARTIAL", "reason": "EXCHANGE_COMPLETENESS_UNATTESTED",
        "source_timeframe": "1m", "source_minutes": expected,
        "parent_dataset_fingerprint": envelope["dataset_fingerprint"],
        "source_revision": envelope["source_revision"],
        "producer_epoch": envelope["producer_epoch"],
        "coverage": {"expected_minutes": expected,
                     "observed_minutes": expected, "missing_minutes": 0},
        "record_integrity": "VERIFIED",
        "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "exchange_completeness": "NOT_ATTESTED",
        "quality_attestation": "NOT_INDEPENDENTLY_ATTESTED",
        "storage_immutability": "NOT_ATTESTED", "immutable": False,
        "read_only": True, "execution_authority": False,
        "trading_authorized": False, "paper_admitted": False,
        "rows": windows,
    }
    # Bound the derived output too; provenance fingerprints never grant trust.
    need(len(canonical(result)) <= 8_388_608, "ROLLUP_RESULT_BYTES")
    return dict(result, dataset_fingerprint=digest(result))
