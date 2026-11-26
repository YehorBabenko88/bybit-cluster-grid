"""Single canonical LAB minute-writer adapter to C's resource-side PG fence.

This is an opt-in, non-service adapter for an *existing* Root-owned psycopg
connection. It does not provision a database, create any lease, connect to an
exchange, start a worker or write raw_capture tables. It is not a production
service authorization; C/E must independently attest native Root/PG authority.

Every INSERT calls the exact C-owned SECURITY DEFINER function on the SAME
already-bound backend. No direct INSERT fallback, conflict-ignore, auto-retry,
transparent reconnect or advisory-lock bypass. Unknown commit outcome is fatal.
"""
import re
import uuid
from datetime import datetime, timezone

from market_data.provenance import canonical
from market_data_v2.qualified_read_contract import validate_minute

_SHA64=re.compile(r"[0-9a-f]{64}\Z")
_FENCE_RESOURCE="grid-market-data-primary"
_FENCE_SCHEMA="lab-postgres-writer-fence.v1"
_OWNER=re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_NAMESPACE=re.compile(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\Z")
_SQL="""SELECT public.lab_fenced_insert(
    %s::text,%s::text,%s::bigint,%s::bigint,%s::uuid,%s::uuid,%s::uuid,
    %s::text,%s::text,%s::text,%s::text,%s::text,%s::bigint,%s::jsonb)"""


class FencedWriterRejected(RuntimeError):
    """Missing, stale, or otherwise unqualified LAB write authority."""


def _deny(condition,code):
    if condition is not True:
        raise FencedWriterRejected(code)


def _uuid4(value):
    _deny(type(value) is str,"FENCE_UUID_REQUIRED")
    try:
        parsed=uuid.UUID(value)
    except (ValueError,AttributeError) as exc:
        raise FencedWriterRejected("FENCE_UUID_REQUIRED") from exc
    _deny(str(parsed)==value and parsed.version==4,"FENCE_UUID_REQUIRED")
    return value


def _sha64(value):
    _deny(type(value) is str and _SHA64.fullmatch(value) is not None,
          "FENCE_SOURCE_DIGEST_REQUIRED")
    return value


def _root_operation_permit_type():
    """Resolve only E's actual Root-owned type; Grid never issues capabilities."""
    try:
        from unified_system.lab_writer_authority import LabWriterOperationPermit
    except ImportError as exc:
        raise FencedWriterRejected("FENCE_E_ROOT_OPERATION_PERMIT_UNAVAILABLE") from exc
    return LabWriterOperationPermit


class CanonicalLabMinuteWriter:
    """One-shot owner-bound connection; no pool and no process orchestration."""

    def __init__(self, connection, *, owner, namespace, generation, token,
                 session_id, instance_id, node_incarnation_id,
                 source_sha256, schema_sha256, native_admission,
                 bound_backend_pid, executor=None, operation_id=None,
                 package_identity=None, bound_backend_start=None):
        _deny(type(owner) is str and _OWNER.fullmatch(owner) is not None,
              "FENCE_OWNER_REQUIRED")
        _deny(type(namespace) is str and len(namespace)<=200
              and _NAMESPACE.fullmatch(namespace) is not None,
              "FENCE_NAMESPACE_REQUIRED")
        _deny(type(generation) is int and 0<generation<2**63
              and type(token) is int and 0<token<2**63,"FENCE_GENERATION_REQUIRED")
        _deny(type(bound_backend_pid) is int and 0<bound_backend_pid<2**31,
              "FENCE_BACKEND_PID_REQUIRED")
        _deny(getattr(connection,"closed",True) is False
              and getattr(connection,"autocommit",None) is True,
              "FENCE_DEDICATED_AUTOCOMMIT_CONNECTION_REQUIRED")
        _deny(callable(getattr(connection,"cursor",None))
              and callable(getattr(connection,"transaction",None)),
              "FENCE_PSYCOG_CONNECTION_REQUIRED")
        _deny(callable(getattr(connection,"rollback",None)),
              "FENCE_TRANSACTION_BOUNDARY_REQUIRED")
        # No caller-supplied True, lab_only, or trusted_root_authority flags.
        # The E Root issuer currently DENIES permit issuance until verified
        # installed-wheel attestation exists. A Python type is not an OS
        # security boundary: E/A own the protected process and C owns SQL.
        _deny(type(native_admission) is _root_operation_permit_type(),
              "FENCE_E_ROOT_OPERATION_PERMIT_REQUIRED")
        _deny(executor is not None and type(operation_id) is str
              and re.fullmatch(r"[0-9a-f]{32}", operation_id) is not None,
              "FENCE_OPERATION_ID_REQUIRED")
        _deny(type(package_identity) is str
              and _SHA64.fullmatch(package_identity) is not None,
              "FENCE_INSTALLED_PACKAGE_IDENTITY_REQUIRED")
        _deny(type(bound_backend_start) is str and bound_backend_start,
              "FENCE_BACKEND_START_REQUIRED")
        try:
            start=datetime.fromisoformat(bound_backend_start.replace("Z","+00:00"))
        except ValueError as exc:
            raise FencedWriterRejected("FENCE_BACKEND_START_REQUIRED") from exc
        _deny(start.tzinfo is not None,
              "FENCE_BACKEND_START_REQUIRED")
        self._connection=connection
        self._authority=native_admission
        self._pid=bound_backend_pid
        self._executor=executor
        self._operation_id=operation_id
        self._package_identity=package_identity
        self._backend_start=bound_backend_start
        self._params=(owner,namespace,generation,token,_uuid4(session_id),
                      _uuid4(instance_id),_uuid4(node_incarnation_id),
                      _sha64(source_sha256),_sha64(schema_sha256))
        self._closed=False
        self._used=False

    def _permit_args(self, content_id):
        return dict(executor=self._executor,operation_id=self._operation_id,
                    content_id=content_id,package_identity=self._package_identity,
                    entrypoint="grid.canonical_lab_fenced_writer",
                    backend_pid=self._pid,backend_start=self._backend_start)

    def _current(self,content_id):
        _deny(not self._closed and not self._used,"FENCE_WRITER_ALREADY_USED")
        _deny(self._connection.closed is False,"FENCE_CONNECTION_CLOSED")
        self._current_after_start(content_id)

    def write(self, record, *, content_id):
        """One transaction; a lost ACK is *not* evidence of a failed commit.

        This method is single-use intentionally. C's exact PG function
        validates owner/namespace/generation/token/session/instance/backend
        identity under a PostgreSQL row lock and refuses old or other backends.
        """
        _deny(type(content_id) is str and _SHA64.fullmatch(content_id) is not None,
              "FENCE_CONTENT_ID_REQUIRED")
        self._current(content_id)
        try:
            item=validate_minute(record,symbol=record["symbol"],before_ms=2**63-1)
        except Exception as exc:
            raise FencedWriterRejected("FENCE_MINUTE_NOT_QUALIFIED") from exc
        _deny(item["status"]=="PARTIAL" and item["source_identity_verified"] is True,
              "FENCE_MINUTE_NOT_QUALIFIED")
        _deny(item["execution_authority"] is False,
              "FENCE_NO_EXECUTION_AUTHORITY_REQUIRED")
        payload=canonical(item).decode("utf-8")
        # No preexisting implicit transaction is permitted: psycopg's
        # transaction() would only create a SAVEPOINT in that case.
        # Fail closed before C's SECURITY DEFINER function is invoked.
        transaction_status=getattr(getattr(self._connection,"info",None),
                                   "transaction_status",None)
        _deny(isinstance(transaction_status,int)
              and not isinstance(transaction_status,bool)
              and transaction_status==0,
              "FENCE_CONNECTION_NOT_IDLE")
        # The caller may not reuse this writer instance after a failed/unknown
        # transaction. New authority must come from the C/E resource owner.
        self._used=True
        try:
            # One protected transaction on the original backend. The lock and
            # last admission check both precede transaction completion.
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_backend_pid(), backend_start::text "
                        "FROM pg_catalog.pg_stat_activity "
                        "WHERE pid=pg_backend_pid() AND usename=session_user")
                    observed=cursor.fetchone()
                    _deny(type(observed) in (tuple,list) and len(observed)==2
                          and type(observed[0]) is int and observed[0]==self._pid
                          and type(observed[1]) is str,
                          "FENCE_BACKEND_CHANGED")
                    try:
                        actual=datetime.fromisoformat(observed[1].replace(" ","T"))
                        expected=datetime.fromisoformat(
                            self._backend_start.replace("Z","+00:00"))
                    except ValueError as exc:
                        raise FencedWriterRejected("FENCE_BACKEND_START_CHANGED") from exc
                    _deny(actual.tzinfo is not None and
                          actual.astimezone(timezone.utc)==
                          expected.astimezone(timezone.utc),
                          "FENCE_BACKEND_START_CHANGED")
                    self._current_after_start(content_id)
                    cursor.execute(_SQL,(*self._params,item["dataset_fingerprint"],
                                         content_id,item["symbol"],item["start_ms"],payload))
                    self._consume_after_sql(content_id)
            return {"schema":"market-data.c-fenced-write-result.v1",
                    "status":"LOCAL_COMMIT_RETURNED","fingerprint":item["dataset_fingerprint"],
                    "storage_immutability":"NOT_ATTESTED",
                    "source_authenticity":"NOT_INDEPENDENTLY_ATTESTED",
                    "exchange_completeness":"NOT_ATTESTED",
                    "execution_authority":False,"trading_authorized":False}
        except BaseException:
            self._closed=True
            try:
                self._connection.rollback()
            except BaseException:
                pass
            raise

    def _current_after_start(self,content_id):
        try:
            accepted=self._authority.require_current(**self._permit_args(content_id))
        except BaseException as exc:
            raise FencedWriterRejected("FENCE_E_OPERATION_REVOKED") from exc
        _deny(accepted is self._authority,"FENCE_E_OPERATION_REVOKED")

    def _consume_after_sql(self,content_id):
        # The same Root permit must be consumed before the transaction exits;
        # the SQL row fence is still the final durable write barrier.
        try:
            accepted=self._authority.consume(**self._permit_args(content_id))
        except BaseException as exc:
            raise FencedWriterRejected("FENCE_E_OPERATION_CONSUME_DENIED") from exc
        _deny(accepted is self._authority,"FENCE_E_OPERATION_CONSUME_DENIED")


def fenced_writer_abi():
    return {"resource_id":_FENCE_RESOURCE,"fence_schema":_FENCE_SCHEMA,
            "sql_function":"public.lab_fenced_insert",
            "postgresql_backend_bound":True,"single_use":True,
            "native_admission":"E_ROOT_ISSUED_ONE_USE_OPERATION_PERMIT",
            "lab_only":True,"trading_authorized":False}
