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

ROUTE = "/internal/v2/candles/qualified"
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
        if urlsplit(self.path).path != ROUTE:
            return super().do_GET()
        if not self._managed_request():
            return
        try:
            if len(self.path.encode("utf-8")) > 2048 or "#" in self.path:
                raise ValueError("invalid route bounds")
            u=urlsplit(self.path)
            if u.path != ROUTE:
                raise ValueError("route mismatch")
            q=parse_qs(u.query,keep_blank_values=True,max_num_fields=3,
                       strict_parsing=True)
            if set(q) not in ({"symbol","limit"},{"symbol","limit","before_ms"}) or any(len(v)!=1 for v in q.values()):
                raise ValueError("explicit query fields required")
            # Require a still-current lease immediately before reading.
            if self.server.startup_admission.require_current() is not True:
                return self._json(503,{"error":"CURRENT_ADMISSION_REQUIRED"})
            result=qualified_snapshot(q["symbol"][0],q["limit"][0],
                                      q.get("before_ms",[None])[0])
            # Deny a post-read lease revocation, avoiding stale read display.
            if self.server.startup_admission.require_current() is not True:
                return self._json(503,{"error":"CURRENT_ADMISSION_REQUIRED"})
            return self._json(200,result)
        except (ValueError,OverflowError):
            return self._json(400,{"error":"INVALID_QUALIFIED_READ_REQUEST"})
        except ProvenanceReadError:
            return self._json(503,{"error":"SOURCE_RECORD_UNQUALIFIED"})
        except Exception:
            return self._json(503,{"error":"QUALIFIED_SOURCE_READ_UNAVAILABLE"})


def main(*,startup_admission=None):
    """Explicit replacement Market Data API entrypoint; no background fork."""
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
