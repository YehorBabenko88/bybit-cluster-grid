"""B Round11 isolated-LAB continuous closed-minute sequencing.

Only the E/Root-owned sealed grant can enable writing. A read-only E status,
caller flags, test doubles or a changed Python object never authorize writes.
C remains the exclusive owner of SQL, durable checkpoint and backend.
"""
import asyncio
from dataclasses import dataclass
from inspect import isawaitable, iscoroutinefunction
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

def _durable_pending(value):
    _identity(value)
    _need(type(value.get('generation')) is int and 0<value['generation']<2**63
          and type(value.get('token')) is int and 0<value['token']<2**63,
          'PENDING_OWNER_GENERATION_INVALID')
    for name in ('source_sha256','schema_sha256'):
        digest=value.get(name)
        _need(type(digest) is str and _SHA.fullmatch(digest) is not None,
              'PENDING_SOURCE_PIN_INVALID')
    return value

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
        _need(iscoroutinefunction(writer_factory) or
              iscoroutinefunction(getattr(writer_factory,"__call__",None)),
              "ROOT_ASYNC_WRITER_FACTORY_REQUIRED")
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
        self._journal_generation=None
        self._journal_backend_pid=None

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
                try:
                    from unified_system.lab_writer_authority import LabWriterGrant
                except ImportError as exc:
                    raise CollectorRejected("E_NATIVE_WRITER_NOT_ADMITTED") from exc
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
            status=await self._guard(write=False)
            self._journal_generation=getattr(self.journal,'generation',None)
            self._journal_backend_pid=getattr(self.journal,'backend_pid',None)
            if self._journal_generation is not None:
                _need(self._journal_generation==status.generation,
                      'JOURNAL_GENERATION_OWNER_MISMATCH')
            try:
                self.pending=await _await(self.journal.pending())
                if self.pending is not None:
                    _durable_pending(self.pending)
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
            _need(iscoroutinefunction(getattr(writer,"write",None)),
                  "ROOT_ASYNC_FENCED_WRITER_REQUIRED")
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

    async def reconcile_after_restart(self,*,fresh_authority=None,fresh_grant=None):
        """Never rebind a stale backend, journal or owner in the same instance.

        The Root supervisor must build a NEW collector+PG journal+executor+
        writer factory under a NEW C generation/E epoch after old backend and
        OS process extinction has been independently established. Calling
        this legacy method never changes state or grants permissions.
        """
        raise CollectorRejected("RECOVERY_REQUIRES_FRESH_ROOT_COHORT")

    async def recover_durable_pending(self, *, previous_generation, previous_epoch,
                                      old_backend_extinct, old_process_extinct):
        """New-instance exact readback reconciliation; no writer or CAS replay.

        `old_*_extinct` are Root-only receipts, not caller boolean flags.
        The E/Root-owned types are checked strictly. Until E exposes both
        proof classes, recovery is disabled rather than trusting duck typing.
        """
        from unified_system.lab_writer_authority import LabWriterGrant
        try:
            from unified_system.lab_writer_revoke import RootBackendExtinction, RootProcessExtinction
        except ImportError as exc:
            raise CollectorRejected("ROOT_EXTINCTION_WITNESS_NOT_AVAILABLE") from exc
        async with self._lock:
            _need(self.state=="HALTED" and type(self.pending) is dict,
                  "DURABLE_PENDING_REQUIRED")
            _need(type(previous_generation) is int and previous_generation>0
                  and type(previous_epoch) is str and _SHA.fullmatch(previous_epoch) is not None,
                  "PREVIOUS_ROOT_IDENTITY_INVALID")
            _need(type(old_backend_extinct) is RootBackendExtinction
                  and type(old_process_extinct) is RootProcessExtinction,
                  "ROOT_EXTINCTION_WITNESS_REQUIRED")
            _need(type(self.writer_grant) is LabWriterGrant,
                  "E_NATIVE_WRITER_NOT_ADMITTED")
            status=await self._guard(write=True)
            _need(status.generation>previous_generation
                  and status.epoch!=previous_epoch,
                  "ROOT_GENERATION_EPOCH_NOT_ROTATED")
            _durable_pending(self.pending)
            _need(self.pending["generation"]==previous_generation,
                  "PENDING_OLD_GENERATION_MISMATCH")
            sym,start,fp,cid=_identity(self.pending)
            minute=Minute(sym,start,fp,cid,{})
            evidence=await _await(self.journal.exact_existing_checkpoint(minute))
            if evidence["state"]=="EXACT_ALREADY_ACKNOWLEDGED":
                await self._guard(write=True)
                await _await(self.journal.clear_pending(minute))
                self.pending=None
                self.state="READY"
                return "CURSOR_ALREADY_ACKNOWLEDGED"
            _need(evidence["state"]=="UNRESOLVED","EXACT_CURSOR_PROOF_INVALID")
            row=await _await(self.journal.readback(minute))
            _need(type(row) is dict and row.get("status")=="MATCH",
                  "UNKNOWN_COMMIT_UNRESOLVED")
            await self._guard(write=True)
            try:
                await _await(self.journal.commit_cursor(minute))
            except BaseException:
                self.state="HALTED";self.last_error="CURSOR_ACK_UNCERTAIN"
                raise
            proof=await _await(self.journal.exact_existing_checkpoint(minute))
            _need(proof["state"]=="EXACT_ALREADY_ACKNOWLEDGED",
                  "CURSOR_NOT_VERIFIED")
            await self._guard(write=True)
            await _await(self.journal.clear_pending(minute))
            self.pending=None
            self.state="READY"
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
                if self.state=="WRITING" or self.attempts>self.max_retry:
                    self.state="HALTED"
                    self.last_error="GAP_RETRY_EXHAUSTED_OR_COMMIT_UNCERTAIN"
                elif self.state!="HALTED":self.state="GAP"
                raise

    async def pump_existing_grid_feed(self, feed, *, max_items=None):
        """Root-drivable sequential feed; never creates a Bybit connection.

        The feed is supplied by Grid existing sole REST/WS transport and
        carries already closed canonical minute candidates. Root supervises
        shutdown/reconnect; this function creates no task or competing client.
        """
        _need(self.state=="READY" and self.pending is None,
              "COLLECTOR_NOT_READY")
        _need(callable(getattr(feed,"__aiter__",None)),
              "EXISTING_GRID_ASYNC_FEED_REQUIRED")
        _need(max_items is None or (type(max_items) is int and 1<=max_items<=100000),
              "PUMP_BUDGET_INVALID")
        await self._guard(write=True)
        processed=0
        try:
            async for item in feed:
                _need(type(item) is tuple and len(item)==2,
                      "GRID_FEED_ITEM_INVALID")
                await self._guard(write=True)
                outcome=await self.deliver(item[0],content_id=item[1])
                if outcome=="GAP":
                    await self.recover_gap()
                processed+=1
                if max_items is not None and processed>=max_items:
                    break
            return {"schema":"grid.lab-feed-pump.v1",
                    "processed_candidates":processed,
                    "exchange_completeness":"NOT_ATTESTED",
                    "trading_authorized":False}
        except BaseException:
            self.state="HALTED"
            if self.last_error is None:
                self.last_error="GRID_FEED_INTERRUPTED_OR_UNCERTAIN"
            raise
    def diagnostic(self):
        return {"schema":"grid.lab-continuous-collector.v3",
                "state":self.state,"error":self.last_error,
                "pending":_key(self.pending)[-1] if self.pending is not None else None,
                "tail":_key(self.tail)[-1] if self.tail is not None else None,
                "native_admitted":False,"trading_authorized":False,
                "exchange_completeness":"NOT_ATTESTED"}
