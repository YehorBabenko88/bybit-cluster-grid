"""Inert, bounded two-walk Bybit linear roster observation via Grid's sole transport.

Two equal cursor walks demonstrate repeatability, NOT independently attested
exchange completeness. No SQL writes, delisting, cutover, or trading authority.
"""
import json
import re
import time
from .instrument_universe import UniverseReadError, _need, _sha

_SYMBOL = re.compile(r"[A-Z0-9]{2,36}\Z")
_FIELD = re.compile(r"[A-Za-z0-9_]{1,40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


async def observe_linear_roster(base_url, *, admission, lease_epoch,
                                fetch_page=None, clock_ms=None,
                                page_limit=1000, max_pages=128, max_symbols=4096):
    """Use existing Grid fetch_linear_instruments_page; optional test seam only.

    A Root admission guard must remain current before/after *every* request.
    The caller supplies an opaque epoch label; it is not an external issuer.
    Both scans must terminate normally with identical ordered page membership
    and identical symbol/status/contract metadata, even if page body hashes differ.
    """
    _need(type(lease_epoch) is str and 0 < len(lease_epoch) <= 128
          and all(32 < ord(ch) < 127 for ch in lease_epoch),
          "GRID_ROSTER_EPOCH_REQUIRED")
    _need(type(page_limit) is int and 1 <= page_limit <= 1000
          and type(max_pages) is int and 1 <= max_pages <= 128
          and type(max_symbols) is int and 1 <= max_symbols <= 50000,
          "GRID_ROSTER_BOUNDS")
    _need(admission is not None and callable(getattr(admission, "require_current", None)),
          "GRID_ROSTER_ROOT_ADMISSION_REQUIRED")
    if fetch_page is None:
        from market_data.bybit import fetch_linear_instruments_page
        fetch_page = fetch_linear_instruments_page
    _need(callable(fetch_page), "GRID_ROSTER_TRANSPORT_REQUIRED")
    if clock_ms is None:
        clock_ms = lambda: int(time.time() * 1000)
    _need(callable(clock_ms), "GRID_ROSTER_CLOCK_REQUIRED")

    def current():
        try:
            admitted = admission.require_current()
        except Exception as exc:
            raise UniverseReadError("GRID_ROSTER_LEASE_REVOKED") from exc
        _need(admitted is True, "GRID_ROSTER_LEASE_REVOKED")

    async def walk():
        cursor = None
        seen_cursors = set()
        seen_symbols = set()
        records = []
        pages = []
        for page_index in range(max_pages):
            current()
            requested = cursor
            try:
                page = await fetch_page(base_url, cursor=cursor, limit=page_limit)
            except Exception as exc:
                raise UniverseReadError("GRID_ROSTER_SOURCE_UNAVAILABLE") from exc
            current()
            items = getattr(page, "items", None)
            next_cursor = getattr(page, "next_cursor", None)
            body = getattr(page, "response", None)
            digest = getattr(body, "body_sha256", None)
            status = getattr(body, "status", None)
            _need(getattr(page, "completeness", None) == "INCOMPLETE"
                  and type(items) in (list, tuple) and 0 < len(items) <= page_limit
                  and type(status) is int and 200 <= status < 300
                  and type(digest) is str and _DIGEST.fullmatch(digest) is not None,
                  "GRID_ROSTER_PAGE_PROVENANCE")
            _need(next_cursor is None or (type(next_cursor) is str
                  and 0 < len(next_cursor) <= 4096
                  and all(32 < ord(ch) < 127 for ch in next_cursor)),
                  "GRID_ROSTER_CURSOR_INVALID")
            _need(next_cursor is None or (next_cursor != requested
                  and next_cursor not in seen_cursors), "GRID_ROSTER_CURSOR_CYCLE")
            subset = []
            for item in items:
                _need(type(item) is dict, "GRID_ROSTER_RECORD_SCHEMA")
                symbol = item.get("symbol")
                state = item.get("status")
                kind = item.get("contractType")
                settle = item.get("settleCoin")
                _need(type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None
                      and type(state) is str and _FIELD.fullmatch(state) is not None
                      and type(kind) is str and _FIELD.fullmatch(kind) is not None
                      and type(settle) is str and _SYMBOL.fullmatch(settle) is not None,
                      "GRID_ROSTER_RECORD_FIELDS")
                _need(symbol not in seen_symbols, "GRID_ROSTER_DUPLICATE_SYMBOL")
                seen_symbols.add(symbol)
                subset.append((symbol, state, kind, settle))
            records.extend(subset)
            _need(len(records) <= max_symbols, "GRID_ROSTER_SYMBOL_LIMIT")
            pages.append({
                "page_index": page_index, "count": len(subset),
                "request_cursor_sha256": _sha(requested),
                "next_cursor_sha256": _sha(next_cursor),
                "body_sha256": digest,
                "records_sha256": _sha(sorted(subset)),
            })
            if next_cursor is None:
                return sorted(records), pages
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise UniverseReadError("GRID_ROSTER_PAGE_LIMIT")

    current()
    first_ms = clock_ms()
    _need(type(first_ms) is int and 0 < first_ms < 2**63,
          "GRID_ROSTER_CLOCK_INVALID")
    first_records, first_pages = await walk()
    second_records, second_pages = await walk()
    current()
    last_ms = clock_ms()
    _need(type(last_ms) is int and first_ms <= last_ms < 2**63,
          "GRID_ROSTER_CLOCK_INVALID")
    _need(first_records == second_records
          and [p["records_sha256"] for p in first_pages]
              == [p["records_sha256"] for p in second_pages],
          "GRID_ROSTER_EPOCH_UNSTABLE")
    result = {
        "schema": "market_data.linear-roster-observation.v1",
        "status": "INFORMATIONAL", "venue": "Bybit", "market_type": "linear",
        "producer": "market_data", "read_only": True,
        "reason": "TWO_CURSOR_WALKS_NOT_INDEPENDENT_COMPLETENESS_PROOF",
        "lease_epoch": lease_epoch,
        "lease_epoch_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "first_observed_ms": first_ms, "last_observed_ms": last_ms,
        "cursor_walks_terminated": 2, "two_walk_roster_equal": True,
        "record_count": len(first_records), "page_count": len(first_pages),
        "records": [dict(symbol=s, status=state, contract_type=kind,
                         settle_coin=settle) for s, state, kind, settle in first_records],
        "page_evidence": first_pages, "roster_sha256": _sha(first_records),
        "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "exchange_completeness": "NOT_ATTESTED", "source_freshness": "OBSERVATION_ONLY",
        "consumer_cutover_authorized": False, "delisting_authorized": False,
        "execution_authority": False, "trading_authorized": False,
        "paper_admitted": False,
    }
    _need(len(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False)) <= 8_388_608,
          "GRID_ROSTER_BYTE_LIMIT")
    return dict(result, dataset_fingerprint=_sha(result))
