"""Opt-in versioned read-only Market Data route on the SAME loopback listener.

No trade API, market network transport, writer, PostgreSQL DDL or new supervisor.
The Root-approved entrypoint replaces the v1 listener rather than launching
another process. Historical market_data v1.1 files remain byte-identical.
"""
import os
import re
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from market_data import history_api
from market_data.admission import startup_identity
from .qualified_read_contract import ProvenanceReadError, qualify_records
from .qualified_rollup import MINUTES, project_qualified_rollup
from .instrument_universe import UniverseReadError, unavailable_universe, recorded_universe_snapshot
from .exchange_roster_epoch import read_root_staged_roster

ROUTE = "/internal/v2/candles/qualified"
ROLLUP_ROUTE = "/internal/v2/candles/qualified-rollup"
HISTORICAL_ROUTE = "/internal/v2/candles/historical-as-of"
EXACT_ROLLUP_ROUTE = "/internal/v2/candles/qualified-rollup-exact"
EXACT_HISTORICAL_ROUTE = "/internal/v2/candles/historical-as-of-exact"
INSTRUMENT_UNIVERSE_ROUTE = "/internal/v2/instruments/universe"
RECORDED_UNIVERSE_ROUTE = "/internal/v2/instruments/recorded"
OBSERVED_UNIVERSE_ROUTE = "/internal/v2/instruments/observed"
_MAX_MS = 9223372036854775807


def qualified_snapshot(symbol, limit, before_ms=None, *, reader=None, now_ms=None):
    """Bounded pure admission of canonical source record bytes, never a trade grant.

    Supplying reader is a test seam. Production uses the canonical PostgreSQL
    read-only market_data.history_api.immutable_minutes path.
    """
    if type(symbol) is not str or history_api.SYMBOL.fullmatch(symbol) is None:
        raise ValueError("QUALIFIED_SYMBOL_REQUIRED")
    if type(limit) is str and re.fullmatch(r"[1-9][0-9]{0,3}",limit):
        limit=int(limit)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("QUALIFIED_LIMIT_REQUIRED")
    if before_ms is None:
        before_ms=_MAX_MS
    elif type(before_ms) is str and re.fullmatch(r"[1-9][0-9]{0,18}",before_ms):
        before_ms=int(before_ms)
    if type(before_ms) is not int or not 0 < before_ms <= _MAX_MS:
        raise ValueError("QUALIFIED_CURSOR_REQUIRED")
    if now_ms is None:
        now_ms=int(time.time()*1000)
    if type(now_ms) is not int or not 0 < now_ms <= _MAX_MS:
        raise ValueError("QUALIFIED_NOW_REQUIRED")
    read=history_api.immutable_minutes if reader is None else reader
    records=read(symbol,limit,before_ms)
    if not records:
        return {
            "schema":"market_data.qualified-read-envelope.v1",
            "api_version":{"major":2,"minor":0},
            "producer":"market_data","read_only":True,"symbol":symbol,
            "timeframe":"1m","limit":limit,"status":"UNAVAILABLE",
            "reason":"SOURCE_PROVENANCE_UNAVAILABLE",
            "record_integrity":"NOT_ESTABLISHED",
            "source_authenticity":"NOT_INDEPENDENTLY_ATTESTED",
            "exchange_completeness":"NOT_ATTESTED",
            "quality_attestation":"NOT_INDEPENDENTLY_ATTESTED",
            "storage_immutability":"NOT_ATTESTED","immutable":False,
            "rows":[],"execution_authority":False,"trading_authorized":False,
            "paper_admitted":False
        }
    result=qualify_records(records,symbol=symbol,before_ms=before_ms,now_ms=now_ms)
    return dict(result, api_version={"major":2,"minor":0}, read_only=True,
                limit=limit,paper_admitted=False)


def qualified_rollup_snapshot(symbol, timeframe, limit, before_ms=None, *, reader=None, now_ms=None, exact=False):
    """Reuse the existing qualified 1m reader with a 75-minute bound."""
    if type(timeframe) is not str or timeframe not in MINUTES:
        raise ValueError("QUALIFIED_ROLLUP_TIMEFRAME_REQUIRED")
    if type(limit) is str and re.fullmatch(r"[1-5]", limit):
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("QUALIFIED_ROLLUP_LIMIT_REQUIRED")
    if type(exact) is not bool:
        raise ValueError("QUALIFIED_ROLLUP_EXACT_MODE_REQUIRED")
    expected = limit * MINUTES[timeframe]
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    # New v2 has an explicit complete-candle UTC cursor contract.
    # Refuse invalid cursors before any PostgreSQL read. Legacy v1 retains
    # its original behavior, because its unchanged consumer may depend on it.
    if exact:
        if (type(now_ms) is not int or not 0 < now_ms < 2**63):
            raise ValueError("QUALIFIED_ROLLUP_EXACT_NOW_REQUIRED")
        if before_ms is not None:
            if type(before_ms) is str and re.fullmatch(r"[1-9][0-9]{0,18}", before_ms):
                before_ms = int(before_ms)
            if (type(before_ms) is not int
                    or not 0 < before_ms <= now_ms
                    or before_ms % (MINUTES[timeframe] * 60000)):
                raise ValueError("QUALIFIED_ROLLUP_EXACT_CURSOR_REQUIRED")
    original = qualified_snapshot(symbol, expected, before_ms, reader=reader, now_ms=now_ms)
    return project_qualified_rollup(original, timeframe=timeframe, limit=limit, now_ms=now_ms, exact=exact)



def historical_asof_snapshot(symbol, timeframe, limit, before_ms, as_of_ms,
                             *, reader=None, now_ms=None, exact=False):
    """Pure source-only historical view; does not grant historical trust.

    Caller fixes an explicit as-of cutoff independent of wall-clock freshness.
    SQL cursor remains a strict upper bound; no NULL/implicit latest snapshot.
    """
    if type(timeframe) is not str or timeframe not in MINUTES:
        raise ValueError("HISTORICAL_TIMEFRAME_REQUIRED")
    if type(limit) is str and re.fullmatch(r"[1-5]", limit):
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("HISTORICAL_LIMIT_REQUIRED")
    if type(exact) is not bool:
        raise ValueError("HISTORICAL_EXACT_MODE_REQUIRED")
    expected = limit * MINUTES[timeframe]
    if type(before_ms) is str and re.fullmatch(r"[1-9][0-9]{0,18}", before_ms):
        before_ms = int(before_ms)
    if type(as_of_ms) is str and re.fullmatch(r"[1-9][0-9]{0,18}", as_of_ms):
        as_of_ms = int(as_of_ms)
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if (type(before_ms) is not int or type(as_of_ms) is not int
            or type(now_ms) is not int
            or not 0 < before_ms <= as_of_ms <= now_ms < 2**63):
        raise ValueError("HISTORICAL_AS_OF_BOUNDS")
    if before_ms % 60000 or as_of_ms % 60000:
        raise ValueError("HISTORICAL_MINUTE_ALIGNMENT")
    # The new lossless historical contract is keyed to FULL 5m/15m candles.
    # Before/as-of remain distinct: as_of is an observation cutoff, not
    # permission to issue a partial bar or imply an authenticated DB snapshot.
    if exact and before_ms % (MINUTES[timeframe] * 60000):
        raise ValueError("HISTORICAL_EXACT_CANDLE_CURSOR_REQUIRED")
    if as_of_ms - before_ms > 30 * 86400000:
        raise ValueError("HISTORICAL_AS_OF_WINDOW_EXCEEDED")
    if type(symbol) is not str or history_api.SYMBOL.fullmatch(symbol) is None:
        raise ValueError("HISTORICAL_SYMBOL_REQUIRED")
    read = history_api.immutable_minutes if reader is None else reader
    records = read(symbol, expected, before_ms)
    if not records:
        raise ProvenanceReadError("HISTORICAL_SOURCE_MISSING")
    result = qualify_records(records, symbol=symbol, before_ms=before_ms,
                             now_ms=now_ms, mode="HISTORICAL_AS_OF",
                             as_of_ms=as_of_ms)
    result = dict(result, api_version={"major":2,"minor":0}, read_only=True,
                  limit=expected, paper_admitted=False, immutable=False,
                  freshness_mode="HISTORICAL_AS_OF", as_of_ms=as_of_ms)
    if result["status"] != "PARTIAL":
        raise ProvenanceReadError("HISTORICAL_SOURCE_NOT_QUALIFIED")
    # Preserve the same bounded 1m -> 5m/15m projection and one Math SDK.
    # Its closed-bar check must use the historical cutoff, not current clock.
    projected = project_qualified_rollup(
        result, timeframe=timeframe, limit=limit, now_ms=as_of_ms, exact=exact)
    # Mark as a distinct informational DTO; historical data is not live-fresh.
    base = {key:value for key,value in projected.items()
            if key != "dataset_fingerprint"}
    base.update(schema=("market_data.historical-as-of-mtf-envelope.v2" if exact
                        else "market_data.historical-as-of-mtf-envelope.v1"),
                freshness_mode="HISTORICAL_AS_OF", as_of_ms=as_of_ms,
                status="PARTIAL", reason="HISTORICAL_AS_OF_SOURCE_ONLY",
                live_freshness="NOT_APPLICABLE",
                historical_source_trust="NOT_INDEPENDENTLY_ATTESTED",
                execution_authority=False, trading_authorized=False,
                paper_admitted=False)
    from market_data.provenance import digest
    return dict(base, dataset_fingerprint=digest(base))


class Handler(history_api.Handler):
    """Retain all v1 handlers and ingress deadlines, add managed v2 read only."""

    def _managed_request(self):
        # Unlike the historical unmanaged development listener, v2 never
        # exposes a qualified route without current Root startup admission.
        if getattr(self.server,"module_identity",None) is None:
            self._json(503,{"error":"MANAGED_SOURCE_ADMISSION_REQUIRED"})
            return False
        return super()._managed_request()

    def do_GET(self):
        # Keep historical v1 GET behavior unchanged except for new v2
        # requirement that the entire replacement listener be Root-managed.
        if urlsplit(self.path).path not in (ROUTE, ROLLUP_ROUTE, HISTORICAL_ROUTE, EXACT_ROLLUP_ROUTE, EXACT_HISTORICAL_ROUTE, INSTRUMENT_UNIVERSE_ROUTE, RECORDED_UNIVERSE_ROUTE, OBSERVED_UNIVERSE_ROUTE):
            return super().do_GET()
        if not self._managed_request():
            return
        try:
            if len(self.path.encode("utf-8")) > 2048 or "#" in self.path:
                raise ValueError("invalid route bounds")
            u=urlsplit(self.path)
            if u.path not in (ROUTE, ROLLUP_ROUTE, HISTORICAL_ROUTE, EXACT_ROLLUP_ROUTE, EXACT_HISTORICAL_ROUTE, INSTRUMENT_UNIVERSE_ROUTE, RECORDED_UNIVERSE_ROUTE, OBSERVED_UNIVERSE_ROUTE):
                raise ValueError("route mismatch")
            if u.path in (INSTRUMENT_UNIVERSE_ROUTE, RECORDED_UNIVERSE_ROUTE, OBSERVED_UNIVERSE_ROUTE):
                if u.query:
                    raise ValueError("instrument universe has no query parameters")
                q={}
            elif u.path in (HISTORICAL_ROUTE, EXACT_HISTORICAL_ROUTE):
                q=parse_qs(u.query,keep_blank_values=True,max_num_fields=5,
                           strict_parsing=True)
                required={"symbol","limit","timeframe","before_ms","as_of_ms"}
                if set(q) != required or any(len(v)!=1 for v in q.values()):
                    raise ValueError("explicit historical query fields required")
                if (q["timeframe"][0] not in MINUTES
                        or re.fullmatch(r"[1-5]", q["limit"][0]) is None):
                    raise ValueError("invalid historical rollup bounds")
            else:
                q=parse_qs(u.query,keep_blank_values=True,
                           max_num_fields=4 if u.path in (ROLLUP_ROUTE, EXACT_ROLLUP_ROUTE) else 3,
                           strict_parsing=True)
                required={"symbol","limit","timeframe"} if u.path in (ROLLUP_ROUTE, EXACT_ROLLUP_ROUTE) else {"symbol","limit"}
                if (set(q) not in (required, required | {"before_ms"})
                        or any(len(v)!=1 for v in q.values())):
                    raise ValueError("explicit query fields required")
                if u.path in (ROLLUP_ROUTE, EXACT_ROLLUP_ROUTE):
                    if q["timeframe"][0] not in MINUTES or re.fullmatch(r"[1-5]", q["limit"][0]) is None:
                        raise ValueError("invalid rollup bounds")
            # Require a still-current lease immediately before reading.
            if self.server.startup_admission.require_current() is not True:
                return self._json(503,{"error":"CURRENT_ADMISSION_REQUIRED"})
            observed_epoch_before=None
            if u.path == INSTRUMENT_UNIVERSE_ROUTE:
                # A stored registry without independently verified exhaustive
                # provenance is NEVER an authorized list for mass delisting.
                # No SQL or exchange reads and no second listener.
                result=unavailable_universe()
            elif u.path == RECORDED_UNIVERSE_ROUTE:
                # Stored registry observation only; NEVER a complete or
                # exchange-authenticated inventory and NEVER a delist grant.
                result=recorded_universe_snapshot()
            elif u.path == OBSERVED_UNIVERSE_ROUTE:
                # No HTTP-triggered exchange or SQL read. A Root-staged
                # informational observation is absent by default.
                # Root must expose its CURRENT epoch, not a cached string.
                # The default managed API has no such extension and denies.
                epoch_reader=getattr(self.server.startup_admission,
                                     "current_roster_epoch", None)
                if not callable(epoch_reader):
                    raise UniverseReadError("GRID_ROSTER_ROOT_EPOCH_UNAVAILABLE")
                observed_epoch_before=epoch_reader()
                result=read_root_staged_roster(
                    getattr(self.server, "roster_observation", None),
                    expected_lease_epoch=observed_epoch_before,
                    now_ms=int(time.time()*1000))
            elif u.path in (HISTORICAL_ROUTE, EXACT_HISTORICAL_ROUTE):
                result=historical_asof_snapshot(
                    q["symbol"][0],q["timeframe"][0],q["limit"][0],
                    q["before_ms"][0],q["as_of_ms"][0],
                    exact=u.path == EXACT_HISTORICAL_ROUTE)
            elif u.path in (ROLLUP_ROUTE, EXACT_ROLLUP_ROUTE):
                result=qualified_rollup_snapshot(
                    q["symbol"][0],q["timeframe"][0],q["limit"][0],
                    q.get("before_ms",[None])[0],
                    exact=u.path == EXACT_ROLLUP_ROUTE)
            else:
                result=qualified_snapshot(q["symbol"][0],q["limit"][0],
                                          q.get("before_ms",[None])[0])
            # Deny a post-read lease revocation, avoiding stale read display.
            if self.server.startup_admission.require_current() is not True:
                return self._json(503,{"error":"CURRENT_ADMISSION_REQUIRED"})
            if observed_epoch_before is not None:
                # Admission may remain TRUE across an epoch handoff: reject
                # stale display if the live Root epoch changed mid-request.
                if epoch_reader() != observed_epoch_before:
                    return self._json(503,{"error":"CURRENT_ADMISSION_REQUIRED"})
            return self._json(503 if u.path == INSTRUMENT_UNIVERSE_ROUTE else 200,result)
        except UniverseReadError:
            return self._json(503,{"error":"UNIVERSE_SOURCE_UNQUALIFIED"})
        except ProvenanceReadError:
            return self._json(503,{"error":"SOURCE_RECORD_UNQUALIFIED"})
        except (ValueError,OverflowError):
            return self._json(400,{"error":"INVALID_QUALIFIED_READ_REQUEST"})
        except Exception:
            return self._json(503,{"error":"QUALIFIED_SOURCE_READ_UNAVAILABLE"})


def main(argv=None, *, startup_admission=None):
    """Root's existing module.main(['serve'], startup_admission=...) ABI.

    This is not an automatic fallback from market_data.cli. Root E must pin
    this module explicitly in its protected source/manifest and keep v1.
    """
    if type(argv) is not list or argv != ["serve"]:
        raise ValueError("ROOT_MANAGED_V2_SERVE_ARGUMENTS_REQUIRED")
    identity=startup_identity(startup_admission)
    if identity is None:
        raise RuntimeError("v2 route requires managed Root admission")
    raw=os.environ.get("MARKET_DATA_PORT","18766")
    if re.fullmatch(r"[1-9][0-9]{0,4}",raw) is None:
        raise ValueError("invalid read API port")
    port=int(raw)
    if not 1 <= port <= 65535:
        raise ValueError("invalid read API port")
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.startup_admission=startup_admission
    server.module_identity=identity
    try:
        server.serve_forever()
    finally:
        server.server_close()
