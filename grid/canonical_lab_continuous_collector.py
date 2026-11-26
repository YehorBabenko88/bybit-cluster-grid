"""B Round11 isolated-LAB continuous closed-minute sequencing.

Only the E/Root-owned sealed grant can enable writing. A read-only E status,
caller flags, test doubles or a changed Python object never authorize writes.
C remains the exclusive owner of SQL, durable checkpoint and backend.
"""
import asyncio
from dataclasses import dataclass
from inspect import isawaitable
import re

_SHA=re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL=re.compile(r"[A-Z0-9_.:-]{2,40}\Z")
_E_SCHEMA="unified.lab-root-writer-authority.v1"
_SCOPE="ISOLATED_LAB_ONLY"

class CollectorRejected(RuntimeError):
    pass

def _need(ok,reason):
    if ok is not True:
        raise CollectorRejected(reason)

async def _await(value):
    _need(isawaitable(value),"ASYNC_OWNER_ABI_REQUIRED")
    return await value

def _identity(value):
    _need(type(value) is dict,"MINUTE_IDENTITY_INVALID")
    symbol=value.get("symbol")
    start=value.get("start_ms")
    fp=value.get("fingerprint",value.get("dataset_fingerprint"))
    cid=value.get("content_id")
    _need(type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None,"INVALID_SYMBOL")
    _need(type(start) is int and 0<=start<2**63 and start%60000==0,"INVALID_MINUTE_START")
    _need(type(fp) is str and _SHA.fullmatch(fp) is not None,"INVALID_FINGERPRINT")
    _need(type(cid) is str and _SHA.fullmatch(cid) is not None,"INVALID_CONTENT_ID")
    return symbol,start,fp,cid

@dataclass(frozen=True)
class Minute:
    symbol: str
    start_ms: int
    fingerprint: str
    content_id: str
    payload: dict

def _minute(record,content_id):
    from market_data_v2.qualified_read_contract import validate_minute
    try:
        item=validate_minute(record,symbol=record["symbol"],before_ms=2**63-1)
    except Exception as exc:
        raise CollectorRejected("CANONICAL_MINUTE_INVALID") from exc
    _need(item["status"]=="PARTIAL" and item["source_identity_verified"] is True
          and item["execution_authority"] is False,"CANONICAL_MINUTE_UNQUALIFIED")
    symbol,start,fp,cid=_identity(dict(symbol=item["symbol"],
        start_ms=item["start_ms"],fingerprint=item["dataset_fingerprint"],
        content_id=content_id))
    return Minute(symbol,start,fp,cid,item)

def _key(m):
    return (m.symbol,m.start_ms,m.fingerprint,m.content_id) if type(m) is Minute else _identity(m)

class ContinuousLabCollector:
    """Single async Root-driven state machine, no transport/connection/lease creation.

    B requires a grant that E has issued from real root/Consul/OS/C evidence,
    never a diagnostic status. Its exact type is imported from E at runtime;
    until E actually publishes that sealed type writes remain DENIED.
    """
    def __init__(self,*,transport,writer_factory,journal,authority,
                 writer_grant=None,stream_id="grid/BTCUSDT/1m",
                 max_backfill=256,max_retry=4):
        for name,obj,methods in (
            ("TRANSPORT",transport,("backfill",)),
            ("WRITER",writer_factory,("__call__",)),
            ("JOURNAL",journal,("pending","checkpoint","append_pending","readback",
                               "commit_cursor","exact_existing_checkpoint","clear_pending")),
            ("AUTHORITY",authority,("check",))):
            _need(all(callable(getattr(obj,m,None)) for m in methods),
                  name+"_REQUIRED")
        _need(type(stream_id) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_:/.-]{0,127}",stream_id) is not None,
              "STREAM_INVALID")
        _need(type(max_backfill) is int and 1<=max_backfill<=10000,"BACKFILL_BOUND_REQUIRED")
        _need(type(max_retry) is int and 0<=max_retry<=16,"RETRY_BOUND_REQUIRED")
        _need(getattr(journal,"stream_id",stream_id)==stream_id,"STREAM_JOURNAL_MISMATCH")
        self.transport=transport
        self.writer_factory=writer_factory
        self.journal=journal
        self.authority=authority
        self.writer_grant=writer_grant
        self.stream_id=stream_id
        self.max_backfill=max_backfill
        self.max_retry=max_retry
        self.state="STOPPED"
        self.pending=None
        self.tail=None
        self._epoch=None
        self.attempts=0
        self.last_error=None
        self._lock=asyncio.Lock()

    async def _guard(self,*,write):
        try:
            status=await _await(self.authority.check())
            from unified_system.lab_writer_authority import LabAuthorityStatus
            _need(type(status) is LabAuthorityStatus and status.schema==_E_SCHEMA
                  and status.scope==_SCOPE and status.state=="READ_ONLY_REVALIDATED_NOT_NATIVE"
                  and type(status.epoch) is str and _SHA.fullmatch(status.epoch) is not None
                  and type(status.generation) is int and status.generation>0
                  and status.native_admitted is False and status.trading_authorized is False,
                  "E_STATUS_REJECTED")
            if self._epoch is None:self._epoch=status.epoch
            _need(status.epoch==self._epoch,"E_EPOCH_CHANGED")
            if write:
                # No fallback to boolean flags, status.native_admitted, or
                # arbitrary user-supplied duck-typed writer_grant.
                from unified_system.lab_writer_authority import LabWriterGrant
                _need(type(self.writer_grant) is LabWriterGrant,"E_NATIVE_WRITER_NOT_ADMITTED")
                grant_status=await _await(self.writer_grant.require_write_current())
                _need(type(grant_status) is LabWriterGrant
                      and grant_status is self.writer_grant
                      and grant_status.epoch==self._epoch,
                      "E_NATIVE_WRITER_NOT_ADMITTED")
            return status
        except asyncio.CancelledError:
            self.state="HALTED";self.last_error="OWNER_CANCELLED"
            raise
        except Exception as exc:
            self.state="HALTED";self.last_error="ROOT_E_AUTHORITY_UNVERIFIED"
            if isinstance(exc,CollectorRejected):raise
            raise CollectorRejected("E_NATIVE_WRITER_NOT_ADMITTED" if write else "ROOT_E_AUTHORITY_UNVERIFIED") from exc

    async def begin(self):
        async with self._lock:
            _need(self.state=="STOPPED","COLLECTOR_ALREADY_STARTED")
            await self._guard(write=False)
            try:
                self.pending=await _await(self.journal.pending())
                if self.pending is not None:
                    _identity(self.pending)
                    self.state="HALTED";self.last_error="DURABLE_PENDING_RECONCILIATION_REQUIRED"
                    return "RECOVERY_REQUIRED"
                checkpoint=await _await(self.journal.checkpoint())
                if checkpoint is not None:_identity(checkpoint)
                self.state="READY"
                return "READ_ONLY_READY"
            except BaseException:
                self.state="HALTED";self.last_error="DURABLE_JOURNAL_UNVERIFIED"
                raise

    def stop(self):
        self.state="HALTED" if self.pending is not None or self.tail is not None else "STOPPED"

    async def _commit(self,minute):
        self.pending=minute
        self.state="WRITING"
        try:
            await self._guard(write=True)
            await _await(self.journal.append_pending(minute))
            await self._guard(write=True)
            # Writer is C-fenced one-shot, provided only by Root. An unknown
            # COMMIT outcome stops this instance. No insert retry.
            writer=await _await(self.writer_factory(minute))
            await self._guard(write=True)
            receipt=await _await(writer.write(minute.payload,content_id=minute.content_id))
            _need(type(receipt) is dict and receipt.get("status")=="LOCAL_COMMIT_RETURNED"
                  and receipt.get("fingerprint")==minute.fingerprint
                  and receipt.get("trading_authorized") is False,
                  "WRITER_RECEIPT_UNQUALIFIED")
            await self._guard(write=True)
            readback=await _await(self.journal.readback(minute))
            _need(type(readback) is dict and readback.get("status")=="MATCH",
                  "COMMITTED_ROW_NOT_PROVEN")
            await self._guard(write=True)
            try:
                await _await(self.journal.commit_cursor(minute))
            except BaseException:
                # Cursor may have committed despite response loss. All recovery
                # proceeds through an exact C owner readback, never a second CAS.
                self.state="HALTED"
                self.last_error="CURSOR_ACK_UNCERTAIN"
                raise
            await self._guard(write=True)
            await _await(self.journal.clear_pending(minute))
        except BaseException:
            self.state="HALTED"
            if self.last_error is None:self.last_error="WRITE_OR_COMMIT_UNCERTAIN"
            raise
        self.pending=None;self.state="READY";self.attempts=0
        return "COMMITTED"

    async def deliver(self,record,*,content_id):
        async with self._lock:
            _need(self.state=="READY" and self.pending is None,"COLLECTOR_NOT_READY")
            await self._guard(write=True)
            minute=_minute(record,content_id)
            cp=await _await(self.journal.checkpoint())
            if cp is not None:
                old=_identity(cp)
                if minute.start_ms<=old[1]:
                    if _key(minute)==old:return "DEDUP"
                    self.state="HALTED";self.last_error="CONFLICT_OR_OLD_MINUTE"
                    raise CollectorRejected("CONFLICT_OR_OLD_MINUTE")
                if minute.start_ms!=old[1]+60000:
                    self.tail=minute;self.state="GAP"
                    return "GAP"
            return await self._commit(minute)

    async def reconcile_after_restart(self,*,fresh_authority,fresh_grant):
        async with self._lock:
            _need(self.state=="HALTED" and self.pending is not None,"NO_DURABLE_PENDING")
            _need(callable(getattr(fresh_authority,"check",None)),"E_ASYNC_AUTHORITY_REQUIRED")
            # Must rebind to a separately issued Root epoch and C backend; an
            # in-memory grant change by itself cannot grant either.
            self.authority=fresh_authority
            self.writer_grant=fresh_grant
            self._epoch=None
            await self._guard(write=True)
            minute=self.pending
            if type(minute) is dict:
                symbol,start,fp,cid=_identity(minute)
                minute=Minute(symbol,start,fp,cid,{})
            evidence=await _await(self.journal.exact_existing_checkpoint(minute))
            if evidence["state"]=="EXACT_ALREADY_ACKNOWLEDGED":
                await self._guard(write=True)
                await _await(self.journal.clear_pending(minute))
                self.pending=None;self.state="READY"
                return "CURSOR_ALREADY_ACKNOWLEDGED"
            if evidence["state"]!="UNRESOLVED":
                raise CollectorRejected("INVALID_RECOVERY_EVIDENCE")
            readback=await _await(self.journal.readback(minute))
            if readback["status"]!="MATCH":
                self.state="HALTED"
                raise CollectorRejected("UNKNOWN_COMMIT_UNRESOLVED")
            await self._guard(write=True)
            # This is the only first CAS after a positive committed-row
            # readback. If its ACK is lost, never automatically replay.
            try:
                await _await(self.journal.commit_cursor(minute))
            except BaseException:
                self.state="HALTED";self.last_error="CURSOR_ACK_UNCERTAIN"
                raise
            proof=await _await(self.journal.exact_existing_checkpoint(minute))
            _need(proof["state"]=="EXACT_ALREADY_ACKNOWLEDGED","CURSOR_NOT_VERIFIED")
            await self._guard(write=True)
            await _await(self.journal.clear_pending(minute))
            self.pending=None;self.state="READY"
            return "RECOVERED_BY_EXACT_ROW"

    async def recover_gap(self):
        async with self._lock:
            _need(self.state=="GAP" and self.tail is not None,"NO_GAP")
            await self._guard(write=True)
            cp=await _await(self.journal.checkpoint())
            _need(cp is not None,"DURABLE_CURSOR_REQUIRED")
            _identity(cp)
            first=cp["start_ms"]+60000
            tail=self.tail
            missing=(tail.start_ms-first)//60000
            _need(0<missing<=self.max_backfill,"GAP_BOUND_EXCEEDED")
            try:
                batch=await _await(self.transport.backfill(tail.symbol,first,
                             tail.start_ms-60000,self.max_backfill))
                _need(type(batch) is list and len(batch)==missing,"BACKFILL_INCOMPLETE")
                validated=[]
                for index,item in enumerate(batch):
                    _need(type(item) is tuple and len(item)==2,"BACKFILL_SHAPE_INVALID")
                    minute=_minute(item[0],item[1])
                    _need(minute.symbol==tail.symbol and minute.start_ms==first+index*60000,
                          "BACKFILL_NOT_CONTIGUOUS")
                    validated.append(minute)
                for minute in validated:
                    await self._guard(write=True)
                    await self._commit(minute)
                await self._guard(write=True)
                result=await self._commit(tail)
                self.tail=None;self.attempts=0
                return result
            except BaseException:
                self.attempts+=1
                if self.state=="WRITING":self.state="HALTED"
                elif self.state!="HALTED":self.state="GAP"
                raise

    def diagnostic(self):
        return {"schema":"grid.lab-continuous-collector.v3",
                "state":self.state,"error":self.last_error,
                "pending":_key(self.pending)[-1] if self.pending is not None else None,
                "tail":_key(self.tail)[-1] if self.tail is not None else None,
                "native_admitted":False,"trading_authorized":False,
                "exchange_completeness":"NOT_ATTESTED"}
