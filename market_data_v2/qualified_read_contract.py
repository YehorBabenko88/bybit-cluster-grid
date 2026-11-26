"""Closed, read-only provenance qualification for Grid v1.1 minute records.

This module grants neither completeness nor execution authority. Callers supply
already-read immutable-looking objects, which are independently revalidated.
"""
import hashlib
import json
import re
import uuid
from market_data.provenance import canonical, digest

_ALLOWED = frozenset(("PARTIAL", "GAP", "STALE", "UNAVAILABLE"))
_RECORD_KEYS = frozenset(("api_version","producer","source","symbol","timeframe",
    "start_ms","end_ms","source_event_start_ms","source_event_end_ms",
    "ingestion_ms","representation","execution_authority","quality_status",
    "quality_reasons","coverage","source_identity_verified","status","reason",
    "candle","levels","dataset_fingerprint"))
_SOURCE_KEYS = frozenset(("identity","source_revision","epoch","market_type","representation"))
_COVERAGE_KEYS = frozenset(("expected_minutes","observed_minutes","missing_minutes",
    "exchange_completeness_attested"))
_CANDLE_KEYS = frozenset(("open","high","low","close","buy_volume","sell_volume",
    "delta","trade_count","poc_price"))
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{2,30}\Z")


class ProvenanceReadError(ValueError):
    """Source record or consumer envelope is not qualified."""


def _require(ok, reason):
    if ok is not True:
        raise ProvenanceReadError(reason)


def _bounded_literal(value, max_bytes=8_388_608):
    # Round-trip rejects exotic mapping/list subclasses, nonfinite JSON,
    # non-JSON objects and cycles before any consumer receives them.
    try:
        raw = canonical(value)
        _require(len(raw) <= max_bytes, "READ_BYTE_BOUND")
        clone = json.loads(raw)
        _require(type(clone) is type(value), "READ_LITERAL_SHAPE")
        return clone
    except (TypeError, ValueError, OverflowError, RecursionError) as e:
        raise ProvenanceReadError("READ_LITERAL_INVALID") from e


def validate_minute(record, *, symbol, before_ms):
    r = _bounded_literal(record, 1_048_576)
    _require(type(r) is dict and set(r) == _RECORD_KEYS, "RECORD_KEYS")
    _require(r["api_version"] == {"major":1,"minor":1}
        and r["producer"] == "market_data" and r["representation"] == "historical_aggregate"
        and r["timeframe"] == "1m", "RECORD_VERSION")
    _require(type(r["symbol"]) is str and _SYMBOL.fullmatch(r["symbol"]) is not None
        and r["symbol"] == symbol, "RECORD_SYMBOL")
    _require(type(r["execution_authority"]) is bool
        and r["execution_authority"] is False, "RECORD_EXECUTION_AUTHORITY")
    source = r["source"]
    _require(type(source) is dict and set(source) == _SOURCE_KEYS, "RECORD_SOURCE")
    try:
        identity=source["identity"]
        _require(type(identity) is str and 1 <= len(identity) <= 256, "RECORD_SOURCE_ID")
        _require(type(source["source_revision"]) is str
            and _SHA40.fullmatch(source["source_revision"]) is not None, "RECORD_REVISION")
        epoch=uuid.UUID(source["epoch"])
        _require(str(epoch) == source["epoch"] and epoch.version == 4, "RECORD_EPOCH")
        _require(source["market_type"] == "linear"
            and source["representation"] == "live_trade_aggregate", "RECORD_SOURCE_KIND")
    except (TypeError, ValueError, AttributeError) as e:
        raise ProvenanceReadError("RECORD_SOURCE_INVALID") from e
    for key in ("start_ms","end_ms","ingestion_ms","source_event_start_ms","source_event_end_ms"):
        _require(type(r[key]) is int and 0 <= r[key] < 2**63, "RECORD_CLOCK")
    start=r["start_ms"];end=r["end_ms"]
    _require(start % 60000 == 0 and end == start+59999
        and start <= r["source_event_start_ms"] <= r["source_event_end_ms"] <= end
        and r["source_event_end_ms"] <= r["ingestion_ms"]
        and start < before_ms, "RECORD_TIME_BOUND")
    _require(type(r["coverage"]) is dict and set(r["coverage"]) == _COVERAGE_KEYS,
        "RECORD_COVERAGE")
    c=r["coverage"]
    _require(type(c["expected_minutes"]) is int and c["expected_minutes"] == 1
        and type(c["observed_minutes"]) is int and c["observed_minutes"] == 1
        and type(c["missing_minutes"]) is int and c["missing_minutes"] == 0
        and c["exchange_completeness_attested"] is False, "RECORD_COMPLETENESS_CLAIM")
    _require(type(r["status"]) is str and r["status"] in ("PARTIAL", "UNAVAILABLE"), "RECORD_STATUS")
    _require((r["status"],r["reason"]) in (
        ("PARTIAL","EXCHANGE_COMPLETENESS_UNATTESTED"),
        ("UNAVAILABLE","SOURCE_PROVENANCE_UNAVAILABLE")), "RECORD_REASON")
    _require(type(r["source_identity_verified"]) is bool,
        "RECORD_SOURCE_ATTESTATION_SHAPE")
    # Hash integrity is NOT independent proof of trusted provider identity.
    _require(type(r["dataset_fingerprint"]) is str
        and _SHA64.fullmatch(r["dataset_fingerprint"]) is not None
        and digest({k:v for k,v in r.items() if k != "dataset_fingerprint"}) == r["dataset_fingerprint"],
        "RECORD_FINGERPRINT")
    _require(type(r["candle"]) is dict and set(r["candle"]) == _CANDLE_KEYS,
        "RECORD_CANDLE_KEYS")
    _require(type(r["levels"]) is list and len(r["levels"]) <= 4096,
        "RECORD_LEVEL_BUDGET")
    from market_math import historical_aggregate_integrity
    candidate={"symbol":r["symbol"],"start_ms":r["start_ms"],
        "source_event_start_ms":r["source_event_start_ms"],
        "source_event_end_ms":r["source_event_end_ms"],
        "source_provenance":source,
        **r["candle"],"levels":r["levels"],
        "quality_status":r["quality_status"],
        "quality_reasons":r["quality_reasons"]}
    _require(historical_aggregate_integrity(candidate) is True,
        "RECORD_NUMERIC_INTEGRITY")
    _require(type(r["quality_status"]) is str and 1 <= len(r["quality_status"]) <= 64
        and type(r["quality_reasons"]) is list and len(r["quality_reasons"]) <= 64
        and all(type(reason) is str and 0 < len(reason) <= 256
                for reason in r["quality_reasons"]), "RECORD_QUALITY")
    _require(r["status"] != "PARTIAL" or r["source_identity_verified"] is True,
        "RECORD_IDENTITY_UNVERIFIED")
    return r


def qualify_records(records, *, symbol, before_ms, now_ms):
    _require(type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None, "QUERY_SYMBOL")
    _require(type(before_ms) is int and 0 < before_ms < 2**63
        and type(now_ms) is int and 0 < now_ms < 2**63, "QUERY_CLOCK")
    _require(type(records) is list and 1 <= len(records) <= 1000,
        "QUERY_RECORD_COUNT")
    validated = [validate_minute(item,symbol=symbol,before_ms=before_ms) for item in records]
    _require(len(canonical(validated)) <= 8_388_608, "QUERY_TOTAL_BYTES")
    starts=[r["start_ms"] for r in validated]
    _require(len(set(starts)) == len(starts), "AMBIGUOUS_MINUTE_REVISIONS")
    ordered=sorted(validated,key=lambda r:r["start_ms"])
    first,last=ordered[0],ordered[-1]
    expected=(last["start_ms"]-first["start_ms"])//60000+1
    _require(0 < expected <= 1000, "QUERY_RANGE")
    epochs={r["source"]["epoch"] for r in ordered}
    revisions={r["source"]["source_revision"] for r in ordered}
    ids={r["source"]["identity"] for r in ordered}
    _require(all(item["source_event_end_ms"] <= now_ms
        and item["ingestion_ms"] <= now_ms for item in ordered), "QUERY_FUTURE_CLOCK")
    unavailable=any(r["status"] == "UNAVAILABLE" for r in ordered)
    missing=expected-len(ordered)
    stale=now_ms-last["source_event_end_ms"] > 120000
    if unavailable:
        status,reason="UNAVAILABLE","SOURCE_PROVENANCE_UNAVAILABLE"
    elif missing or len(epochs)!=1 or len(revisions)!=1 or len(ids)!=1:
        status,reason="GAP","MISSING_MINUTES_OR_EPOCH_CHANGE"
    elif stale:
        status,reason="STALE","FRESHNESS_WATERMARK_EXPIRED"
    else:
        status,reason="PARTIAL","EXCHANGE_COMPLETENESS_UNATTESTED"
    # A valid single observed minute does not prove whole-exchange completeness.
    return {
        "schema":"market_data.qualified-read-envelope.v1",
        "api_version":{"major":1,"minor":1},
        "producer":"market_data",
        "symbol":symbol,"timeframe":"1m",
        "status":status,"reason":reason,
        "record_integrity":"VERIFIED",
        "source_declared_quality":sorted({item["quality_status"] for item in ordered}),
        "quality_attestation":"NOT_INDEPENDENTLY_ATTESTED",
        "source_authenticity":"NOT_INDEPENDENTLY_ATTESTED",
        "exchange_completeness":"NOT_ATTESTED",
        "coverage":{"expected_minutes":expected,"observed_minutes":len(ordered),
            "missing_minutes":missing},
        "freshness_utc_ms":last["source_event_end_ms"],
        "source_revision":next(iter(revisions)) if len(revisions)==1 else None,
        "producer_epoch":next(iter(epochs)) if len(epochs)==1 else None,
        "dataset_fingerprint":digest(ordered),
        "rows":ordered if not unavailable else [],
        "immutable":False,"storage_immutability":"NOT_ATTESTED",
        "execution_authority":False,"trading_authorized":False,
    }
