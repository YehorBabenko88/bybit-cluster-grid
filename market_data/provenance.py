"""Source-owned immutable minute records. Digests are integrity, never authentication."""
import copy
import hashlib
import json
import re
import time
import uuid
from market_math import historical_aggregate_integrity

SHA = re.compile(r"^[0-9a-f]{40}$")

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def producer(identity, revision, endpoint):
    # Market identity derives from the subscribed endpoint, never caller inference.
    return {"identity": identity, "source_revision": revision,
            "epoch": str(uuid.uuid4()),
            "market_type": "linear" if endpoint == "wss://stream.bybit.com/v5/public/linear" else None,
            "representation": "live_trade_aggregate"}


def data_integrity(row):
    """Math owns numeric partition/POC policy; this layer owns JSON byte bounds."""
    try:
        return historical_aggregate_integrity(row) and len(canonical(row)) <= 1048576
    except (TypeError, ValueError, OverflowError):
        return False

def _minute_record_base(row, ingestion_ms, authenticated_identity=None):
    row = copy.deepcopy(row)
    source = row.get("source_provenance", {})
    valid = (isinstance(source, dict) and isinstance(source.get("identity"), str)
             and bool(source["identity"]) and SHA.fullmatch(str(source.get("source_revision", "")))
             and source.get("market_type") == "linear"
             and source.get("representation") == "live_trade_aggregate")
    try:
        uuid.UUID(source.get("epoch", ""))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if authenticated_identity is not None and source.get("identity") != authenticated_identity:
        valid = False
    event_start, event_end = row.get("source_event_start_ms"), row.get("source_event_end_ms")
    start = row.get("start_ms")
    valid = bool(valid and type(start) is int and type(event_start) is int and type(event_end) is int
                 and start >= 0 and start % 60000 == 0 and start <= event_start <= event_end < start + 60000
                 and type(ingestion_ms) is int and event_end <= ingestion_ms)
    integral = data_integrity(row)
    valid = valid and integral
    record = {"api_version": {"major": 1, "minor": 1}, "producer": "market_data",
              "source": source, "symbol": row["symbol"], "timeframe": "1m",
              "start_ms": start, "end_ms": start + 59999,
              "source_event_start_ms": event_start, "source_event_end_ms": event_end,
              "ingestion_ms": ingestion_ms, "representation": "historical_aggregate",
              "execution_authority": False, "quality_status": row.get("quality_status", "UNKNOWN") if integral else "INVALID",
              "quality_reasons": row.get("quality_reasons", []),
              "coverage": {"expected_minutes": 1, "observed_minutes": 1, "missing_minutes": 0,
                           "exchange_completeness_attested": False},
              "source_identity_verified": authenticated_identity is not None and valid,
              "status": "PARTIAL" if valid else "UNAVAILABLE",
              "reason": "EXCHANGE_COMPLETENESS_UNATTESTED" if valid else "SOURCE_PROVENANCE_UNAVAILABLE",
              "candle": {k: row[k] for k in ("open", "high", "low", "close", "buy_volume", "sell_volume", "delta", "trade_count", "poc_price")},
              "levels": row["levels"]}
    # Observing trades cannot attest exchange-wide completeness; never synthesize AVAILABLE.
    return record

def minute_record(row, ingestion_ms, authenticated_identity=None):
    record=_minute_record_base(row,ingestion_ms,authenticated_identity)
    record['dataset_fingerprint']=digest(record)
    return record

def minute_record_v12(row,ingestion_ms,authenticated_identity=None,*,available_at_ms,units):
    """Opt-in actual turnover declaration; never infer availability or quote units.

    This pure factory neither writes records nor upgrades stored v1.1 bytes.
    Raw collector/writer wiring and authenticated receipts remain separate gates.
    """
    from .history_contract import (_snapshot_json,_clock,_units,_record,
        TURNOVER_BASIS,AVAILABILITY_BASIS,FINANCIAL_ENCODING)
    try:
        row,units=_snapshot_json((row,units),max_bytes=1048576)
        if type(row) is not dict:raise ValueError('TURNOVER_HISTORY_LITERAL_ROW_REQUIRED')
        units=_units(units);known=_clock(available_at_ms);_clock(ingestion_ms);start=_clock(row['start_ms'])
        if known<start+60000:raise ValueError('TURNOVER_HISTORY_AVAILABILITY_REQUIRED')
        if type(row['turnover_basis']) is not str or row['turnover_basis']!=TURNOVER_BASIS:raise ValueError('TURNOVER_HISTORY_ACTUAL_NOTIONAL_BASIS_REQUIRED')
        # Existing source and aggregate validation is shared byte-for-byte with
        # legacy output. New declarations are added only to this new version.
        record=_minute_record_base(row,ingestion_ms,authenticated_identity)
        record.update(api_version={'major':1,'minor':2},units=units,available_at_ms=known,
            turnover_basis=TURNOVER_BASIS,availability_basis=AVAILABILITY_BASIS,
            financial_encoding=FINANCIAL_ENCODING,source_authentication='NOT_EVALUATED',trading_authorized=False)
        record['candle']['turnover']=row['turnover']
        _record(record)
        record['dataset_fingerprint']=digest(record)
        return record
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('TURNOVER_MINUTE_UNAVAILABLE') from exc

async def persist_minute(conn, row, authenticated_identity=None):
    record = minute_record(row, int(time.time()*1000), authenticated_identity)
    await conn.execute("""INSERT INTO provenance_minutes(fingerprint,content_id,symbol,start_ms,record)
        VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT DO NOTHING""",
        record["dataset_fingerprint"], digest(row), row["symbol"], row["start_ms"], canonical(record).decode())
    return record
