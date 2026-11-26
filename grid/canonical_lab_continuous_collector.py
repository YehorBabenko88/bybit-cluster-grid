"""Fail-closed asynchronous Grid LAB candle coordinator.

B owns sequencing only. C owns durable PostgreSQL checkpoints and single
fenced writer; E owns Root/Consul/OS admission. This class cannot create leases,
connections, SQL tables, processes, or alternate Bybit REST/WebSocket clients.
"""
from dataclasses import dataclass
from inspect import isawaitable
import re

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9_.:-]{2,40}\Z")
_E_SCHEMA = "unified.lab-root-writer-authority.v1"
_SCOPE = "ISOLATED_LAB_ONLY"

class CollectorRejected(RuntimeError):
    pass

def _need(ok, reason):
    if ok is not True:
        raise CollectorRejected(reason)

async def _await(value):
    if not isawaitable(value):
        raise CollectorRejected("ASYNC_OWNER_ABI_REQUIRED")
    return await value

def _sha(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None,
          "INVALID_DIGEST")

@dataclass(frozen=True)
class Minute:
    symbol: str
    start_ms: int
    fingerprint: str
    content_id: str
    payload: dict

def _identity(value):
    _need(type(value) is dict, "PENDING_IDENTITY_INVALID")
    symbol = value.get("symbol")
    start = value.get("start_ms")
    fingerprint = value.get("fingerprint",value.get("dataset_fingerprint"))
    content_id = value.get("content_id")
    _need(type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None,
          "INVALID_SYMBOL")
    _need(type(start) is int and 0 <= start < 2**63 and start % 60000 == 0,
          "INVALID_MINUTE_START")
    _sha(fingerprint)
    _sha(content_id)
    return (symbol,start,fingerprint,content_id)

def _minute(record,content_id):
    _need(type(record) is dict and record.get("status") == "PARTIAL"
          and record.get("execution_authority") is False
          and record.get("trading_authorized") is False
          and record.get("paper_admitted") is False,
          "NOT_DISPLAY_ONLY")
    from market_data_v2.qualified_read_contract import validate_minute
    try:
        qualified=validate_minute(record,symbol=record["symbol"],
                                  before_ms=2**63-1)
    except Exception as exc:
        raise CollectorRejected("CANONICAL_MINUTE_INVALID") from exc
    _need(qualified.get("status")=="PARTIAL" and
          qualified.get("source_identity_verified") is True,
          "CANONICAL_MINUTE_UNQUALIFIED")
    identity = dict(record,content_id=content_id,
                    fingerprint=record.get("dataset_fingerprint"))
    symbol,start,fp,cid=_identity(identity)
    return Minute(symbol,start,fp,cid,record)

def _same(a,b):
    return _identity(a)==_identity(b)

class ContinuousLabCollector:
    """Async, Root-driven and intentionally non-actuating before E grant.

    journal C-owner adapter contract (all async): checkpoint(), pending(),
    append_pending(minute), readback(minute), commit_cursor(minute),
    clear_pending(minute). readback returns exact C dict with status
    MATCH/MISSING/CONFLICT and fixed fields. commit_cursor returns exact
    C custody receipt; no cursor ACK from a local writer result.
    authority must provide E async check() returning typed LabAuthorityStatus.
    writer_grant is a *separate* Root-owned future capability: no grant exists
    in E current release, so no native Grid writes can start today.
    """
    def __init__(self, *, transport, writer_factory, journal, authority,
                 writer_grant=None, stream_id="grid/BTCUSDT/1m",
                 max_backfill=256, max_retry=4):
        _need(type(stream_id) is str and 1<=len(stream_id)<=128,
              "STREAM_REQUIRED")
        for label,obj,methods in (
            ("TRANSPORT",transport,("backfill",)),
            ("WRITER",writer_factory,("__call__",)),
            ("JOURNAL",journal,("checkpoint","pending","append_pending",
                                "readback","commit_cursor","clear_pending")),
            ("AUTHORITY",authority,("check",)),
        ):
            _need(all(callable(getattr(obj,name,None)) for name in methods),
                  label+"_REQUIRED")
        _need(type(max_backfill) is int and 1<=max_backfill<=10000,
              "BACKFILL_BOUND_REQUIRED")
        _need(type(max_retry) is int and 0<=max_retry<=16,
              "RETRY_BOUND_REQUIRED")
        self.transport=transport
        self.writer_factory=writer_factory
        self.journal=journal
        self.authority=authority
        self.writer_grant=writer_grant
        self.stream_id=stream_id
        self.max_backfill=max_backfill
        self.max_retry=max_retry
        self.attempts=0
        self.state="STOPPED"
        self.pending=None
        self.tail=None
        self.last_error=None
        self._epoch=None

    async def _owner(self,*,write):
        try:
            status=await _await(self.authority.check())
            from unified_system.lab_writer_authority import LabAuthorityStatus
            _need(type(status) is LabAuthorityStatus
                  and status.schema==_E_SCHEMA and status.scope==_SCOPE
                  and status.state=="READ_ONLY_REVALIDATED_NOT_NATIVE"
                  and type(status.epoch) is str and len(status.epoch)==64
                  and _SHA.fullmatch(status.epoch) is not None
                  and type(status.generation) is int
                  and status.generation>0
                  and status.native_admitted is False
                  and status.trading_authorized is False,
                  "E_STATUS_REJECTED")
            if self._epoch is None:
                self._epoch=status.epoch
            _need(self._epoch==status.epoch,"E_EPOCH_CHANGED")
            # E's current diagnostic result is NEVER sufficient for a
            # write permit. Existing E runtime unconditionally DENIES.
            if write:
                _need(False,"E_NATIVE_WRITER_NOT_ADMITTED")
            return status
        except Exception as exc:
            self.state="HALTED"
            self.last_error="ROOT_E_AUTHORITY_UNVERIFIED"
            if isinstance(exc,CollectorRejected):
                raise
            raise CollectorRejected("ROOT_E_AUTHORITY_UNVERIFIED") from exc

    async def begin(self):
        _need(self.state=="STOPPED","COLLECTOR_ALREADY_STARTED")
        await self._owner(write=False)
        try:
            self.pending=await _await(self.journal.pending())
            if self.pending is not None:
                _identity(self.pending)
                self.state="HALTED"
                self.last_error="DURABLE_PENDING_RECONCILIATION_REQUIRED"
                return "RECOVERY_REQUIRED"
            checkpoint=await _await(self.journal.checkpoint())
            if checkpoint is not None:
                _identity(checkpoint)
            self.state="READY"
            return "READ_ONLY_READY"
        except BaseException:
            self.state="HALTED"
            self.last_error="DURABLE_JOURNAL_UNVERIFIED"
            raise

    def stop(self):
        self.state="HALTED" if self.pending is not None else "STOPPED"
        if self.pending is not None:
            self.last_error="DURABLE_PENDING_RECONCILIATION_REQUIRED"

    async def deliver(self,record,*,content_id):
        _need(self.state=="READY","COLLECTOR_NOT_READY")
        # Fail closed before transforming a candidate or mutating a C journal.
        await self._owner(write=True)
        raise CollectorRejected("E_NATIVE_WRITER_NOT_ADMITTED")

    async def recover_gap(self):
        await self._owner(write=True)
        raise CollectorRejected("E_NATIVE_WRITER_NOT_ADMITTED")

    async def reconcile_after_restart(self,*,fresh_authority):
        _need(self.state=="HALTED" and self.pending is not None,
              "NO_DURABLE_PENDING")
        _need(callable(getattr(fresh_authority,"check",None)),
              "E_ASYNC_AUTHORITY_REQUIRED")
        # A different Python object does not imply a fresh Consul/PG epoch.
        self.authority=fresh_authority
        await self._owner(write=False)
        _need(False,"E_NATIVE_WRITER_NOT_ADMITTED")

    def diagnostic(self):
        return {"schema":"grid.lab-continuous-collector.v2",
                "state":self.state,"error":self.last_error,
                "pending":self.pending.get("content_id") if
                type(self.pending) is dict else None,
                "native_admitted":False,
                "trading_authorized":False,
                "exchange_completeness":"NOT_ATTESTED"}
