"""Async scheduling wrapper for the existing ONE C-fenced PostgreSQL writer.

Root constructs the exact existing CanonicalLabMinuteWriter using its owned
connection, C fence, same-backend identity and E grant. Grid never creates a
DB connection, mints authority or executes a new SQL statement. This wrapper
only dispatches the one-shot writer on Root's LabOwnerExecutor serial lane.
After any unknown outcome the wrapper is permanently unusable.
"""
from .canonical_lab_continuous_collector import CollectorRejected, _need
from .canonical_lab_fenced_writer import CanonicalLabMinuteWriter

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
                  and receipt.get("execution_authority") is False
                  and receipt.get("trading_authorized") is False,
                  "C_FENCED_WRITER_RECEIPT_UNQUALIFIED")
            return receipt
        except BaseException:
            self._poisoned=True
            # Owner executor is poisoned on timeout/cancellation; never queue
            # another SQL action against an ambiguous commit/backend.
            raise
