"""LAB-only continuous market-data coordination; no service, network or SQL owner.

C owns the fenced writer and durable journal; E owns revocable admission and
process lifecycle. The Grid transport passed here must be the existing Grid
transport. No constructor opens a network socket, starts tasks or provisions DB.
"""
from dataclasses import dataclass
import hashlib
import json

class CollectorRejected(RuntimeError):
    pass

@dataclass(frozen=True)
class Minute:
    symbol: str
    start_ms: int
    fingerprint: str
    content_id: str
    payload: object

def _need(value, code):
    if value is not True:
        raise CollectorRejected(code)

def _sha(value):
    _need(type(value) is str and len(value)==64 and
          all(c in "0123456789abcdef" for c in value), "INVALID_DIGEST")

def _minute(record, content_id):
    _need(type(record) is dict and type(record.get("symbol")) is str and
          record["symbol"].isalnum() and 1<=len(record["symbol"])<=64,
          "INVALID_SYMBOL")
    _need(type(record.get("start_ms")) is int and
          record["start_ms"]>=0 and record["start_ms"]%60000==0,
          "INVALID_MINUTE_START")
    fingerprint=record.get("dataset_fingerprint")
    _sha(fingerprint);_sha(content_id)
    _need(record.get("status")=="PARTIAL" and
          record.get("execution_authority") is False and
          record.get("trading_authorized") is False,
          "NOT_DISPLAY_ONLY")
    return Minute(record["symbol"],record["start_ms"],fingerprint,content_id,record)

class ContinuousLabCollector:
    """Single-consumer deterministic coordinator with owner-supplied interfaces.

    journal contract: read(symbol) -> mapping {start_ms, fingerprint, content_id}
    or None; append_pending(minute)->None; confirm(minute)->None;
    reconcile(minute)->"MATCH"|"ABSENT"|"CONFLICT"|"UNKNOWN".
    Implementations must durably fence journal updates with C SQL authority.
    No claims of durable delivery are made until journal.confirm returns.
    writer_factory(minute) returns one NEW C-fenced writer, never a pool or raw
    SQL connection. E authority.require_current must be true on each boundary.
    """
    def __init__(self, *, transport, writer_factory, journal, authority,
                 max_backfill=256, max_retry=4):
        for name,obj,methods in (
            ("TRANSPORT",transport,("backfill",)),
            ("WRITER",writer_factory,("__call__",)),
            ("JOURNAL",journal,("read","append_pending","confirm","reconcile")),
            ("AUTHORITY",authority,("require_current",)),
        ):
            _need(all(callable(getattr(obj,m,None)) for m in methods),
                  name+"_REQUIRED")
        _need(type(max_backfill) is int and 1<=max_backfill<=10000,
              "BACKFILL_BOUND_REQUIRED")
        _need(type(max_retry) is int and 0<=max_retry<=16,
              "RETRY_BOUND_REQUIRED")
        self.transport=transport
        self.writer_factory=writer_factory
        self.journal=journal
        self.authority=authority
        self.max_backfill=max_backfill
        self.max_retry=max_retry
        self.state="STOPPED"
        self.pending=None
        self.attempts=0
        self.last_error=None

    def _authorized(self):
        try:
            current=self.authority.require_current()
        except Exception as exc:
            self.state="HALTED";self.last_error="AUTHORITY_REVOKED"
            raise CollectorRejected("AUTHORITY_REVOKED") from exc
        if current is not True:
            self.state="HALTED";self.last_error="AUTHORITY_REVOKED"
            raise CollectorRejected("AUTHORITY_REVOKED")

    def begin(self):
        _need(self.state=="STOPPED" and self.pending is None,
              "PENDING_REQUIRES_OWNER_RECONCILIATION")
        self._authorized()
        self.state="READY"

    def stop(self):
        # Never erase the recovery state after an uncertain write or a gap.
        if self.pending is not None:
            self.state="HALTED"
            self.last_error="PENDING_REQUIRES_OWNER_RECONCILIATION"
            return
        self.state="STOPPED"

    def deliver(self,record,*,content_id):
        _need(self.state=="READY","COLLECTOR_NOT_READY")
        self._authorized()
        m=_minute(record,content_id)
        _need(self.pending is None,"PENDING_UNRESOLVED")
        prior=self.journal.read(m.symbol)
        if prior is not None:
            _need(type(prior) is dict and type(prior.get("start_ms")) is int,
                  "JOURNAL_CORRUPT")
            if prior["start_ms"]>=m.start_ms:
                if (prior["start_ms"]==m.start_ms and
                    prior.get("fingerprint")==m.fingerprint and
                    prior.get("content_id")==m.content_id):
                    return "DEDUP"
                self.state="HALTED";self.last_error="CONFLICT_OR_OLD_MINUTE"
                raise CollectorRejected("CONFLICT_OR_OLD_MINUTE")
            if m.start_ms-prior["start_ms"]>60000:
                self.state="GAP";self.pending=m
                return "GAP"
        self.journal.append_pending(m)
        self.pending=m
        self.state="WRITING"
        try:
            self._authorized()
            writer=self.writer_factory(m)
            _need(callable(getattr(writer,"write",None)),"C_FENCED_WRITER_REQUIRED")
            receipt=writer.write(m.payload,content_id=m.content_id)
            _need(type(receipt) is dict and receipt.get("status")=="LOCAL_COMMIT_RETURNED"
                  and receipt.get("fingerprint")==m.fingerprint and
                  receipt.get("execution_authority") is False
                  and receipt.get("trading_authorized") is False,
                  "WRITE_RECEIPT_UNQUALIFIED")
            self._authorized()
            result=self.journal.reconcile(m)
            _need(result=="MATCH","READBACK_NOT_PROVEN")
            self.journal.confirm(m)
        except BaseException:
            self.state="HALTED";self.last_error="WRITE_OR_COMMIT_UNCERTAIN"
            raise
        self.pending=None
        self.state="READY"
        return "COMMITTED"

    def reconcile_after_restart(self,*,new_authority):
        """Reconciliation never replays unknown writes or mints new authority."""
        _need(self.state=="HALTED" and self.pending is not None,
              "NO_UNRESOLVED_WRITE")
        _need(callable(getattr(new_authority,"require_current",None)),
              "FRESH_ROOT_AUTHORITY_REQUIRED")
        self.authority=new_authority
        self._authorized()
        outcome=self.journal.reconcile(self.pending)
        if outcome=="MATCH":
            self.journal.confirm(self.pending)
            self.pending=None
            self.state="READY"
            return "RECONCILED"
        # ABSENT may be a raced/unknown read, never blind replay.
        self.state="HALTED";self.last_error="UNKNOWN_COMMIT_UNRESOLVED"
        raise CollectorRejected("UNKNOWN_COMMIT_UNRESOLVED")

    async def recover_gap(self):
        _need(self.state=="GAP" and self.pending is not None,"NO_GAP")
        self._authorized()
        current=self.journal.read(self.pending.symbol)
        _need(type(current) is dict and type(current.get("start_ms")) is int,
              "DURABLE_CURSOR_REQUIRED")
        first=current["start_ms"]+60000
        missing=(self.pending.start_ms-first)//60000
        _need(missing>0 and missing<=self.max_backfill,"GAP_BOUND_EXCEEDED")
        try:
            # Existing Grid transport only; the callback cannot independently
            # grant exchange completeness or write a second store.
            pages=await self.transport.backfill(self.pending.symbol,first,
                                                self.pending.start_ms-60000,
                                                self.max_backfill)
        except BaseException:
            self.attempts+=1
            if self.attempts>self.max_retry:
                self.state="HALTED"
            raise
        _need(type(pages) is list and len(pages)==missing,"BACKFILL_INCOMPLETE")
        expected=first
        for item in pages:
            _need(type(item) is tuple and len(item)==2,"BACKFILL_INVALID")
            candidate=_minute(item[0],item[1])
            _need(candidate.symbol==self.pending.symbol and
                  candidate.start_ms==expected,"BACKFILL_NOT_CONTIGUOUS")
            expected+=60000
        tail=self.pending;self.pending=None;self.state="READY"
        for record,content_id in pages:
            self.deliver(record,content_id=content_id)
        return self.deliver(tail.payload,content_id=tail.content_id)

    def diagnostic(self):
        return {"schema":"grid.lab-continuous-collector.v1",
                "state":self.state,"error":self.last_error,
                "pending":self.pending.content_id if self.pending else None,
                "native_admitted":False,"trading_authorized":False,
                "exchange_completeness":"NOT_ATTESTED"}
