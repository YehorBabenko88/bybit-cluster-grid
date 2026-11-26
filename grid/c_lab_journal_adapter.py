"""B-owned async adapter over C's ONLY protected PostgreSQL checkpoint API.

No SQL, no PG connection, no lease issuance, no writer grant. C's functions are
called exclusively through the already owner-validated C object and identity.
This adapter cannot admit native writes; it is inert until Root/E binds a true
revocable owner authority to its lifecycle (not available in Round10).
"""
from inspect import isawaitable
from .canonical_lab_continuous_collector import CollectorRejected,_identity,_need

class COwnedLabJournal:
    def __init__(self, *, c_module, pg, identity, generation, backend_pid, stream_id):
        required=("read_lab_pending","read_lab_checkpoint","append_lab_pending",
                  "read_committed_lab_minute","commit_verified_lab_cursor",
                  "clear_verified_lab_pending","verify_existing_lab_checkpoint")
        _need(all(callable(getattr(c_module,n,None)) for n in required),
              "C_CANONICAL_CHECKPOINT_API_REQUIRED")
        _need(type(generation) is int and generation>0
              and type(backend_pid) is int and backend_pid>1,
              "C_OWNER_GENERATION_BACKEND_REQUIRED")
        _need(type(stream_id) is str and stream_id,"C_STREAM_REQUIRED")
        self.c=c_module;self.pg=pg;self.identity=identity
        self.generation=generation;self.backend_pid=backend_pid;self.stream_id=stream_id

    async def _call(self,method,**values):
        # Sync PG commands are owned by C, not B. No async loop blocking
        # should occur in service mode: Root must supply a dedicated executor
        # and an asynchronously adapted C facade before native use.
        fn=getattr(self.c,method)
        result=fn(self.pg,**values)
        if isawaitable(result):
            raise CollectorRejected("C_SYNC_OWNER_FACADE_REQUIRED")
        return result

    def _scope(self):
        return dict(identity=self.identity,generation=self.generation,
                    backend_pid=self.backend_pid)
    def _key(self,minute):
        if isinstance(minute,dict):
            symbol,start,fp,cid=_identity(minute)
        else:
            symbol,start,fp,cid=minute.symbol,minute.start_ms,minute.fingerprint,minute.content_id
        return dict(symbol=symbol,start_ms=start,fingerprint=fp,content_id=cid)

    async def pending(self):
        item=await self._call("read_lab_pending",stream_id=self.stream_id)
        if item is not None:
            _identity(item)
            _need(item.get("source_sha256")==self.identity.source_sha256
                  and item.get("schema_sha256")==self.identity.schema_sha256
                  and type(item.get("generation")) is int
                  and type(item.get("token")) is int,
                  "C_PENDING_SOURCE_OR_OWNER_CHANGED")
        return item

    async def checkpoint(self):
        item=await self._call("read_lab_checkpoint",stream_id=self.stream_id)
        if item is not None:_identity(item)
        return item

    async def append_pending(self,minute):
        receipt=await self._call("append_lab_pending",**self._scope(),
                     stream_id=self.stream_id,**self._key(minute))
        _need(type(receipt) is dict and
              receipt.get("schema")=="lab-pg-pending-append.v1"
              and receipt.get("stream_id")==self.stream_id
              and receipt.get("native_admitted") is False,
              "C_PENDING_RECEIPT_UNQUALIFIED")
        return receipt

    async def readback(self,minute):
        result=await self._call("read_committed_lab_minute",
                               **self._scope(),**self._key(minute))
        _need(type(result) is dict
              and result.get("schema")=="lab-pg-committed-readback.v1"
              and result.get("status") in ("MATCH","MISSING","CONFLICT")
              and result.get("native_admitted") is False,
              "C_READBACK_UNQUALIFIED")
        key=self._key(minute)
        _need(all(result.get(name)==value for name,value in key.items()),
              "C_READBACK_IDENTITY_MISMATCH")
        return result

    async def commit_cursor(self,minute):
        key=self._key(minute)
        result=await self._call("commit_verified_lab_cursor",**self._scope(),
              stream_id=self.stream_id,cursor=key["start_ms"],**key)
        _need(type(result) is dict
              and result.get("schema")=="lab-pg-durable-cursor.v1"
              and result.get("cursor")==key["start_ms"]
              and result.get("fingerprint")==key["fingerprint"]
              and result.get("content_id")==key["content_id"]
              and result.get("committed_record_verified") is True
              and result.get("native_admitted") is False,
              "C_CURSOR_RECEIPT_UNQUALIFIED")
        return result

    async def exact_existing_checkpoint(self,minute):
        result=await self._call("verify_existing_lab_checkpoint",**self._scope(),
              stream_id=self.stream_id,**self._key(minute))
        _need(type(result) is dict
              and result.get("schema")=="lab-pg-exact-checkpoint-reconciliation.v1"
              and result.get("state") in ("EXACT_ALREADY_ACKNOWLEDGED","UNRESOLVED")
              and result.get("native_admitted") is False,
              "C_EXISTING_CURSOR_UNQUALIFIED")
        key=self._key(minute)
        _need(all(result.get(name)==value for name,value in key.items()),
              "C_EXISTING_CURSOR_IDENTITY_MISMATCH")
        return result

    async def clear_pending(self,minute):
        # This C function itself rechecks committed checkpoint/active owner.
        result=await self._call("clear_verified_lab_pending",**self._scope(),
                                stream_id=self.stream_id)
        _need(result is True,"C_PENDING_CLEAR_UNVERIFIED")
        return result
