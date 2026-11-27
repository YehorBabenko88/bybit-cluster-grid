"""Fail-closed five-filter observational Bybit roster via Grid's sole HTTP reader.

All five successful bounded status-filter walks are still self-observations,
not an independently witnessed exchange inventory. Never delist or cut over.
No new transport, supervisor, SQL, file or trading operations.
"""
import json
import time
from .instrument_universe import UniverseReadError, _need, _sha
from .exchange_roster_epoch import observe_linear_roster
from market_data.bybit import _LINEAR_STATUS_QUERY

_STATUSES = tuple(sorted(_LINEAR_STATUS_QUERY))


async def observe_linear_status_segments(base_url, *, admission, lease_epoch,
                                         fetch_page=None, clock_ms=None,
                                         page_limit=1000, max_pages=128,
                                         max_symbols=4096, max_window_ms=600000):
    """Two full status cycles, two complete cursor walks per status per cycle.

    A missing/empty status is represented explicitly; no missing status is
    guessed complete. Two consistent observations DO NOT authenticate Bybit.
    """
    _need(_STATUSES == ("Closed", "Delivering", "PendingOpen", "PreLaunch", "Trading"),
          "GRID_ROSTER_STATUS_ENUM_CHANGED")
    _need(type(max_symbols) is int and 1 <= max_symbols <= 50000
          and type(max_window_ms) is int and 1 <= max_window_ms <= 600000,
          "GRID_ROSTER_SEGMENT_BOUNDS")
    _need(admission is not None and callable(getattr(admission, "require_current", None)),
          "GRID_ROSTER_ROOT_ADMISSION_REQUIRED")
    if clock_ms is None:
        clock_ms = lambda: int(time.time() * 1000)
    _need(callable(clock_ms), "GRID_ROSTER_CLOCK_REQUIRED")
    if fetch_page is None:
        from market_data.bybit import fetch_linear_instruments_page
        fetch_page = fetch_linear_instruments_page
    _need(callable(fetch_page), "GRID_ROSTER_TRANSPORT_REQUIRED")

    def current():
        try:
            granted = admission.require_current()
        except Exception as exc:
            raise UniverseReadError("GRID_ROSTER_SEGMENT_LEASE_REVOKED") from exc
        _need(granted is True, "GRID_ROSTER_SEGMENT_LEASE_REVOKED")

    current()
    started = clock_ms()
    _need(type(started) is int and 0 < started < 2**63,
          "GRID_ROSTER_SEGMENT_CLOCK_INVALID")
    cycles = []
    for cycle in range(2):
        received = {}
        for status in _STATUSES:
            current()
            part = await observe_linear_roster(
                base_url, admission=admission, lease_epoch=lease_epoch,
                status=status, fetch_page=fetch_page, clock_ms=clock_ms,
                page_limit=page_limit, max_pages=max_pages,
                max_symbols=max_symbols, max_window_ms=max_window_ms)
            _need(part["status"] == "INFORMATIONAL"
                  and part["source_status_query"] == status
                  and part["all_exchange_statuses_enumerated"] is False
                  and part["exchange_completeness"] == "NOT_ATTESTED"
                  and part["consumer_cutover_authorized"] is False
                  and part["delisting_authorized"] is False
                  and part["lease_epoch"] == lease_epoch,
                  "GRID_ROSTER_SEGMENT_INFORMATIONAL_ONLY")
            received[status] = part
        cycles.append(received)
    current()
    finished = clock_ms()
    _need(type(finished) is int and started <= finished < 2**63
          and finished - started <= max_window_ms,
          "GRID_ROSTER_SEGMENT_WINDOW")
    all_records = []
    seen_symbols = set()
    evidence = []
    for status in _STATUSES:
        first, second = cycles[0][status], cycles[1][status]
        # Distinct from two self-walks within a single status observation.
        _need(first["records"] == second["records"]
              and first["roster_sha256"] == second["roster_sha256"]
              and first["record_count"] == second["record_count"]
              and first["page_count"] == second["page_count"]
              and [(p["count"], p["records_sha256"],
                    p["request_cursor_sha256"], p["next_cursor_sha256"])
                   for p in first["page_evidence"]]
                  == [(p["count"], p["records_sha256"],
                       p["request_cursor_sha256"], p["next_cursor_sha256"])
                      for p in second["page_evidence"]],
              "GRID_ROSTER_CROSS_CYCLE_DRIFT")
        for row in first["records"]:
            _need(row["status"] == status,
                  "GRID_ROSTER_SEGMENT_STATUS_MISMATCH")
            symbol = row["symbol"]
            _need(symbol not in seen_symbols,
                  "GRID_ROSTER_CROSS_STATUS_DUPLICATE")
            seen_symbols.add(symbol)
            all_records.append(row)
        _need(len(all_records) <= max_symbols,
              "GRID_ROSTER_SEGMENT_TOTAL_LIMIT")
        evidence.append({
            "status": status, "record_count": first["record_count"],
            "page_count": first["page_count"],
            "roster_sha256": first["roster_sha256"],
            "cursor_walks_terminated": 4,
            "first_observation_fingerprint": first["dataset_fingerprint"],
            "second_observation_fingerprint": second["dataset_fingerprint"],
        })
    result = {
        "schema": "market_data.linear-roster-status-segments.v1",
        "status": "INFORMATIONAL", "read_only": True,
        "venue": "Bybit", "market_type": "linear", "producer": "market_data",
        "source": "EXPLICIT_FIVE_STATUS_FILTER_TWO_CYCLE_OBSERVATION",
        "lease_epoch": lease_epoch,
        "first_observed_ms": started, "last_observed_ms": finished,
        "queried_statuses": list(_STATUSES),
        "status_evidence": evidence,
        "records": sorted(all_records, key=lambda row: row["symbol"]),
        "record_count": len(all_records),
        "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "exchange_completeness": "NOT_ATTESTED",
        "independent_witness_verified": False,
        "delisting_authorized": False,
        "consumer_cutover_authorized": False,
        "execution_authority": False,
        "trading_authorized": False,
        "paper_admitted": False,
    }
    _need(len(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)) <= 8_388_608,
          "GRID_ROSTER_SEGMENT_BYTE_LIMIT")
    return dict(result, dataset_fingerprint=_sha(result))
