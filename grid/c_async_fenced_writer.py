"""Async scheduling wrapper for the existing ONE C-fenced PostgreSQL writer.

Root constructs the exact existing CanonicalLabMinuteWriter using its owned
connection, C fence, same-backend identity and E grant. Grid never creates a
DB connection, mints authority or executes a new SQL statement. This wrapper
only dispatches the one-shot writer on Root's LabOwnerExecutor serial lane.
After any unknown outcome the wrapper is permanently unusable.
"""
from .canonical_lab_continuous_collector import CollectorRejected, _need
from .canonical_lab_fenced_writer import CanonicalLabMinuteWriter
from market_data.provenance import digest
from market_data_v2.qualified_read_contract import validate_minute

class AsyncCanonicalFencedWriter:
    __slots__=("_writer","_executor","_used","_poisoned")
    def __init__(self, *, writer, owner_executor):
        from unified_system.lab_owner_executor import LabOwnerExecutor
        _need(type(writer) is CanonicalLabMinuteWriter,
              "EXACT_C_FENCED_WRITER_REQUIRED")
        _need(type(owner_executor) is LabOwnerExecutor,
              "ROOT_SERIAL_WRITER_EXECUTOR_REQUIRED")
        self._writer=writer
        self._executor=owner_executor
        self._used=False
        self._poisoned=False

    async def write(self, record, *, content_id):
        _need(not self._used and not self._poisoned,
              "C_FENCED_WRITER_ALREADY_USED_OR_UNCERTAIN")
        try:
            item=validate_minute(record,symbol=record["symbol"],before_ms=2**63-1)
            _need(type(content_id) is str and content_id==digest(item),
                  "CANONICAL_CONTENT_ID_REQUIRED")
        except CollectorRejected:
            raise
        except Exception as exc:
            raise CollectorRejected("CANONICAL_MINUTE_REQUIRED") from exc
        self._used=True
        try:
            # Exactly one SQL call path: existing C-owned SECURITY DEFINER
            # public.lab_fenced_insert invoked by the one-shot writer.
            receipt=await self._executor.call(
                lambda: self._writer.write(record,content_id=content_id),
                timeout=10.0)
            _need(type(receipt) is dict
                  and receipt.get("schema")=="market-data.c-fenced-write-result.v1"
                  and receipt.get("status")=="LOCAL_COMMIT_RETURNED"
                  and receipt.get("content_id")==content_id
                  and receipt.get("fingerprint")==item["dataset_fingerprint"]
                  and receipt.get("execution_authority") is False
                  and receipt.get("trading_authorized") is False,
                  "C_FENCED_WRITER_RECEIPT_UNQUALIFIED")
            return receipt
        except BaseException:
            self._poisoned=True
            # Owner executor is poisoned on timeout/cancellation; never queue
            # another SQL action against an ambiguous commit/backend.
            raise

class RootCanonicalWriterFactory:
    """The collector's ONE Root-provided async factory for the ONE C writer.

    Root/E supplies the exact owned connection, C identity and protected
    attestation inputs. This class does not issue grants, open SQL connections,
    register a process or create an alternate writer. E alone may issue a
    bounded one-record operation permit after native verification.
    """
    __slots__=("authority","owner_executor","connection","identity",
               "generation","token","epoch","backend_pid","backend_start",
               "package_identity","_uncertain")

    def __init__(self, *, authority, owner_executor, connection, identity,
                 generation, token, epoch, backend_pid, backend_start,
                 package_identity):
        from unified_system.lab_writer_authority import LabWriterAuthority
        from unified_system.lab_owner_executor import LabOwnerExecutor
        import re
        _need(type(authority) is LabWriterAuthority and
              type(owner_executor) is LabOwnerExecutor and
              owner_executor is authority._executor,
              "E_EXACT_ROOT_FACTORY_AUTHORITY_REQUIRED")
        _need(type(generation) is int and generation>0 and
              type(token) is int and token>0 and type(backend_pid) is int and
              backend_pid>1 and type(epoch) is str and
              re.fullmatch(r"[0-9a-f]{64}",epoch) is not None and
              type(backend_start) is str and bool(backend_start) and
              type(package_identity) is str and
              re.fullmatch(r"[0-9a-f]{64}",package_identity) is not None,
              "ROOT_FACTORY_EXACT_OPERATION_BINDING_REQUIRED")
        _need(callable(getattr(authority,"issue_operation_permit",None)),
              "E_OPERATION_ISSUER_REQUIRED")
        _need(getattr(identity,"owner",None)==authority._identity.owner and
              getattr(identity,"namespace",None)==authority._identity.namespace and
              getattr(identity,"token",None)==token and
              authority._generation==generation and
              authority._epoch==epoch and authority._backend_pid==backend_pid,
              "ROOT_FACTORY_SQL_IDENTITY_MISMATCH")
        self.authority=authority
        self.owner_executor=owner_executor
        self.connection=connection
        self.identity=identity
        self.generation=generation
        self.token=token
        self.epoch=epoch
        self.backend_pid=backend_pid
        self.backend_start=backend_start
        self.package_identity=package_identity
        self._uncertain=False

    async def __call__(self, minute):
        """Return the original one-shot async writer, not a second SQL path."""
        import secrets
        from .canonical_lab_continuous_collector import Minute
        _need(not self._uncertain and type(minute) is Minute,
              "ROOT_FACTORY_MINUTE_REQUIRED")
        _need(minute.content_id==digest(minute.payload) and
              minute.symbol==minute.payload["symbol"] and
              minute.start_ms==minute.payload["start_ms"] and
              minute.fingerprint==minute.payload["dataset_fingerprint"],
              "ROOT_FACTORY_CANONICAL_IDENTITY_MISMATCH")
        self._uncertain=True
        # The original Root issuer performs live C/Consul checks and must
        # return ONLY a protected installed-wheel-bound typed operation permit.
        operation_id=secrets.token_hex(16)
        permit=await self.authority.issue_operation_permit(
            executor=self.owner_executor,operation_id=operation_id,
            content_id=minute.content_id,package_identity=self.package_identity,
            entrypoint="grid.canonical_lab_fenced_writer",
            symbol=minute.symbol,start_ms=minute.start_ms,
            fingerprint=minute.fingerprint)
        from unified_system.lab_writer_authority import LabWriterOperationPermit
        _need(type(permit) is LabWriterOperationPermit,
              "E_EXACT_OPERATION_PERMIT_REQUIRED")
        def bind_original_writer():
            return CanonicalLabMinuteWriter(
                self.connection,owner=self.identity.owner,
                namespace=self.identity.namespace,
                generation=self.generation,token=self.token,
                session_id=self.identity.session_id,
                instance_id=self.identity.instance_id,
                node_incarnation_id=self.identity.node_incarnation_id,
                source_sha256=self.identity.source_sha256,
                schema_sha256=self.identity.schema_sha256,
                native_admission=permit,bound_backend_pid=self.backend_pid,
                executor=self.owner_executor,
                operation_id=operation_id,
                package_identity=self.package_identity,
                bound_backend_start=self.backend_start,epoch=self.epoch)
        try:
            raw=await self.owner_executor.call(bind_original_writer,timeout=3.0)
            _need(type(raw) is CanonicalLabMinuteWriter,
                  "ROOT_FACTORY_WRITER_CONSTRUCTION_REJECTED")
            bound=AsyncCanonicalFencedWriter(
                writer=raw,owner_executor=self.owner_executor)
            self._uncertain=False
            return bound
        except BaseException:
            permit.revoke()
            raise
