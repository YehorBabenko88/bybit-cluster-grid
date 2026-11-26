"""Negative LAB-only contract checks for Grid's C-owned SQL fence adapter.

The stub is *not* real PostgreSQL. Native PG18 tests must prove actual
SECURITY DEFINER function ownership, revocation and durable high-water.
No network, exchange, DB or service access in this file.
"""
import unittest
import uuid
import copy
from enum import IntEnum
from types import SimpleNamespace
from unittest.mock import patch

from market_data.provenance import minute_record,producer,digest
from grid.canonical_lab_fenced_writer import (
    CanonicalLabMinuteWriter,FencedWriterRejected,fenced_writer_abi,
)

NOW=1800000120000
START=(NOW//60000-1)*60000
VALUES={
    "owner":"unified-system","namespace":"unified/lab",
    "generation":1,"token":100,
    "session_id":"e8b0b9fd-b3cf-4b10-9c0f-85cf474b4bca",
    "instance_id":"4dfaa80e-c521-449b-8629-697d8f93c08e",
    "node_incarnation_id":"be924684-ad63-4d6f-82bb-84d55bb4e3f5",
    "source_sha256":"a"*64,"schema_sha256":"b"*64,
    "bound_backend_pid":1234,
}


def _make_record():
    src=producer("fixture","a"*40,"wss://stream.bybit.com/v5/public/linear")
    row={
      "symbol":"BTCUSDT","start_ms":START,
      "source_event_start_ms":START+1,"source_event_end_ms":START+59000,
      "source_provenance":src,
      "open":1.0,"high":2.0,"low":1.0,"close":2.0,
      "buy_volume":1.0,"sell_volume":0.0,"delta":1.0,
      "trade_count":1,"poc_price":2.0,"quality_status":"GOOD",
      "quality_reasons":[],
      "levels":[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
                 "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}],
    }
    return minute_record(row,NOW,"fixture")


_RECORD = _make_record()
def record():
    return copy.deepcopy(_RECORD)


class Admission:
    """Synthetic E-shape ONLY for negative unit logic, never native authority."""
    def __init__(self,*values):
        self.values=list(values or [True,True,True])
        self.calls=0
        self.used=False
        self.kwargs=[]
    def require_current(self,**kwargs):
        self.calls+=1
        self.kwargs.append(kwargs)
        valid=(not self.used and (self.values.pop(0) if self.values else False))
        return self if valid else False
    def consume(self,**kwargs):
        result=self.require_current(**kwargs)
        if result is self:
            self.used=True
        return result


class Connection:
    closed=False
    autocommit=True
    def __init__(self,*,pid=1234,fail_sql=False,fail_commit=False):
        self.pid=pid
        self.fail_sql=fail_sql
        self.fail_commit=fail_commit
        self.calls=[]
        self.rollback_calls=0
        self.info=SimpleNamespace(transaction_status=0)
    def cursor(self):
        connection=self
        class Cursor:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def execute(self,sql,args=None):
                connection.calls.append((sql,args))
                if connection.fail_sql and "lab_fenced_insert" in sql:
                    raise RuntimeError("DATABASE_FENCE_REJECTED")
            def fetchone(self):return (connection.pid,"2026-11-26 20:00:00+00")
        return Cursor()
    def transaction(self):
        connection=self
        class Transaction:
            def __enter__(self):
                connection.calls.append(("BEGIN",None))
                return self
            def __exit__(self,exc_type,exc,tb):
                connection.calls.append(("COMMIT" if exc_type is None else "ROLLBACK",None))
                if exc_type is None and connection.fail_commit:
                    raise RuntimeError("UNKNOWN_POSTGRES_COMMIT_OUTCOME")
                return False
        return Transaction()
    def rollback(self):
        self.rollback_calls+=1


def writer(conn=None,auth=None,**updates):
    args={**VALUES,**updates}
    args.setdefault("executor",object())
    args.setdefault("operation_id","d"*32)
    args.setdefault("package_identity","e"*64)
    args.setdefault("bound_backend_start","2026-11-26T20:00:00+00:00")
    args.setdefault("epoch","f"*64)
    return CanonicalLabMinuteWriter(conn or Connection(),
                                    native_admission=auth if auth is not None else Admission(),
                                    **args)


class CanonicalLabFencedWriterTests(unittest.TestCase):
    def setUp(self):
        # Exact mock substitution applies only to unit tests. E's real type
        # and protected issuer are mandatory in installed Grid runtime.
        self.mock_permit=patch(
            "grid.canonical_lab_fenced_writer._root_operation_permit_type",
            return_value=Admission)
        self.mock_permit.start()
        self.addCleanup(self.mock_permit.stop)
    def test_only_exact_sql_security_definer_function_on_same_backend(self):
        c=Connection();a=Admission()
        result=writer(c,a).write(record(),content_id=digest(record()))
        self.assertEqual(result["status"],"LOCAL_COMMIT_RETURNED")
        self.assertFalse(result["execution_authority"])
        self.assertFalse(result["trading_authorized"])
        self.assertEqual(a.calls,3)
        self.assertEqual(c.calls[0][0],"BEGIN")
        self.assertIn("pg_backend_pid()",c.calls[1][0])
        self.assertIn("public.lab_fenced_insert(",c.calls[2][0])
        self.assertEqual(c.calls[-1][0],"COMMIT")
        self.assertEqual(len(c.calls[2][1]),14)
        self.assertEqual(c.calls[2][1][0:4],("unified-system","unified/lab",1,100))
        self.assertFalse(any("INSERT INTO" in cmd for cmd,_ in c.calls))

    def test_reject_bad_owner_namespace_and_generation_before_sql(self):
        for diff in ({"owner":"foreign owner"},{"namespace":"../bad"},
                     {"generation":True},{"token":0},{"token":2**63},
                     {"source_sha256":"invalid"},{"schema_sha256":"A"*64},
                     {"session_id":"invalid"},{"node_incarnation_id":str(uuid.uuid1())}):
            c=Connection()
            with self.subTest(diff=diff),self.assertRaises(FencedWriterRejected):
                writer(c,**diff)
            self.assertEqual(c.calls,[])

    def test_deny_no_auth_and_nonlab_authority(self):
        c=Connection()
        with self.assertRaisesRegex(
                FencedWriterRejected,"FENCE_E_ROOT_OPERATION_PERMIT_REQUIRED"):
            CanonicalLabMinuteWriter(c,native_admission=None,**VALUES)
        for admission in (SimpleNamespace(require_current=lambda:True),
                          SimpleNamespace(lab_only=True,trusted_root_authority=True,
                                          require_current=lambda:True)):
            with self.subTest(admission=admission),self.assertRaisesRegex(
                    FencedWriterRejected,"FENCE_E_ROOT_OPERATION_PERMIT_REQUIRED"):
                writer(c,admission)
        class UserForgedSubclass(Admission):
            pass
        with self.assertRaisesRegex(
                FencedWriterRejected,"FENCE_E_ROOT_OPERATION_PERMIT_REQUIRED"):
            writer(c,UserForgedSubclass())
        self.assertEqual(c.calls,[])

    def test_deny_automatic_transaction_pooled_and_closed_connection(self):
        for diff in ({"autocommit":False},{"closed":True}):
            c=Connection()
            for k,v in diff.items():setattr(c,k,v)
            with self.subTest(diff=diff),self.assertRaises(FencedWriterRejected):
                writer(c)
            self.assertEqual(c.calls,[])

    def test_psycopg_transaction_status_intenum_idle_is_valid(self):
        class TransactionStatus(IntEnum):
            IDLE=0
            ACTIVE=1
        c=Connection()
        c.info.transaction_status=TransactionStatus.IDLE
        result=writer(c).write(record(),content_id=digest(record()))
        self.assertEqual(result["status"],"LOCAL_COMMIT_RETURNED")
        c2=Connection()
        c2.info.transaction_status=TransactionStatus.ACTIVE
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_CONNECTION_NOT_IDLE"):
            writer(c2).write(record(),content_id=digest(record()))
        self.assertEqual(c2.calls,[])
        c3=Connection()
        c3.info.transaction_status=True
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_CONNECTION_NOT_IDLE"):
            writer(c3).write(record(),content_id=digest(record()))
        self.assertEqual(c3.calls,[])

    def test_ambient_transaction_denied_before_any_fenced_sql(self):
        c=Connection();c.info.transaction_status=2
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_CONNECTION_NOT_IDLE"):
            writer(c).write(record(),content_id=digest(record()))
        self.assertEqual(c.calls,[])
        self.assertEqual(c.rollback_calls,0)

    def test_deny_revoked_before_backend_observation(self):
        c=Connection();a=Admission(False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_E_OPERATION_REVOKED"):
            writer(c,a).write(record(),content_id=digest(record()))
        self.assertEqual(c.calls,[])

    def test_deny_changed_backend_and_close_unknown_outcome(self):
        c=Connection(pid=5678);w=writer(c)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_BACKEND_CHANGED"):
            w.write(record(),content_id=digest(record()))
        self.assertEqual(len(c.calls),3)
        self.assertEqual(c.calls[0][0],"BEGIN")
        self.assertIn("pg_backend_pid()",c.calls[1][0])
        self.assertEqual(c.calls[2][0],"ROLLBACK")
        self.assertEqual(c.rollback_calls,1)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_WRITER_ALREADY_USED"):
            w.write(record(),content_id=digest(record()))

    def test_revoke_after_backend_check_rolls_back_without_sql(self):
        c=Connection();a=Admission(True,False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_E_OPERATION_REVOKED"):
            writer(c,a).write(record(),content_id=digest(record()))
        self.assertFalse(any("lab_fenced_insert" in sql for sql,_ in c.calls))
        self.assertEqual(c.calls[-1][0],"ROLLBACK")

    def test_revoke_after_function_before_commit_rolls_back(self):
        c=Connection();a=Admission(True,True,False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_E_OPERATION_CONSUME_DENIED"):
            writer(c,a).write(record(),content_id=digest(record()))
        self.assertEqual(len([sql for sql,_ in c.calls if "lab_fenced_insert" in sql]),1)
        self.assertEqual(c.calls[-1][0],"ROLLBACK")

    def test_sql_rejection_and_unknown_commit_are_fatal_no_retry(self):
        for kwargs in ({"fail_sql":True},{"fail_commit":True}):
            c=Connection(**kwargs);w=writer(c)
            with self.subTest(kwargs=kwargs),self.assertRaises(RuntimeError):
                w.write(record(),content_id=digest(record()))
            self.assertEqual(len([sql for sql,_ in c.calls if "lab_fenced_insert" in sql]),1)
            with self.assertRaises(FencedWriterRejected):
                w.write(record(),content_id=digest(record()))

    def test_invalid_record_and_trading_promotion_never_write(self):
        for modify in ({"producer":"bybit-cluster-grid"},{"execution_authority":True}):
            c=Connection();r=record();r.update(modify)
            r["dataset_fingerprint"]=digest({k:v for k,v in r.items() if k!="dataset_fingerprint"})
            with self.subTest(modify=modify),self.assertRaisesRegex(FencedWriterRejected,"FENCE_MINUTE_NOT_QUALIFIED"):
                writer(c).write(r,content_id=digest(record()))
            self.assertEqual(c.calls,[])

    def test_async_sealed_grant_cannot_be_misread_as_sync_true(self):
        class AsyncGrant:
            lab_only=True
            trusted_root_authority=True
            async def require_current(self):
                return True
        c=Connection()
        with self.assertRaisesRegex(
                FencedWriterRejected,"FENCE_E_ROOT_OPERATION_PERMIT_REQUIRED"):
            writer(c,AsyncGrant())
        self.assertEqual(c.calls,[])

    def test_backend_start_mismatch_aborts_before_fenced_sql(self):
        c=Connection()
        with self.assertRaisesRegex(FencedWriterRejected,
                                    "FENCE_BACKEND_START_CHANGED"):
            writer(c,bound_backend_start="2026-11-26T21:00:00+00:00").write(
                record(),content_id=digest(record()))
        self.assertEqual(c.calls[-1][0],"ROLLBACK")
        self.assertFalse(any("lab_fenced_insert" in sql for sql,_ in c.calls))

    def test_one_operation_content_binding_and_consumption(self):
        c=Connection(); a=Admission()
        writer(c,a).write(record(),content_id=digest(record()))
        self.assertTrue(a.used)
        self.assertEqual(a.calls,3)
        self.assertEqual(len(a.kwargs),3)
        self.assertTrue(all(k["content_id"]==digest(record()) for k in a.kwargs))
        self.assertTrue(all(k["operation_id"]=="d"*32 for k in a.kwargs))
        self.assertTrue(all(k["package_identity"]=="e"*64 for k in a.kwargs))
        self.assertTrue(all(k["backend_pid"]==1234 for k in a.kwargs))
        self.assertTrue(all(k["symbol"]=="BTCUSDT" and k["start_ms"]==START for k in a.kwargs))
        self.assertTrue(all(k["fingerprint"]==record()["dataset_fingerprint"] for k in a.kwargs))
        self.assertTrue(all(k["owner"]==VALUES["owner"] and k["namespace"]==VALUES["namespace"] for k in a.kwargs))
        self.assertTrue(all(k["generation"]==1 and k["token"]==100 and k["epoch"]=="f"*64 for k in a.kwargs))

    def test_replayed_one_use_writer_never_second_insert(self):
        c = Connection()
        w = writer(c, Admission())
        self.assertEqual(
            w.write(record(), content_id=digest(record()))["status"],
            "LOCAL_COMMIT_RETURNED")
        with self.assertRaisesRegex(
                FencedWriterRejected, "FENCE_WRITER_ALREADY_USED"):
            w.write(record(), content_id=digest(record()))
        self.assertEqual(sum(
            "lab_fenced_insert" in sql for sql, _ in c.calls), 1)

    def test_mismatched_content_digest_denied_before_e_or_sql(self):
        c=Connection();a=Admission()
        with self.assertRaisesRegex(FencedWriterRejected,
                                    "FENCE_CONTENT_ID_RECORD_MISMATCH"):
            writer(c,a).write(record(),content_id="0"*64)
        self.assertEqual(a.calls,0)
        self.assertEqual(c.calls,[])

    def test_epoch_required_before_any_sql(self):
        c=Connection()
        with self.assertRaisesRegex(FencedWriterRejected,
                                    "FENCE_E_ROOT_EPOCH_REQUIRED"):
            writer(c,epoch="INVALID")
        self.assertEqual(c.calls,[])

    def test_sql_tuple_tampering_denied_by_exact_e_permit(self):
        class Bound(Admission):
            def require_current(self,**kwargs):
                if kwargs["generation"]!=1 or kwargs["token"]!=100:
                    return False
                return super().require_current(**kwargs)
        c=Connection();a=Bound()
        with patch("grid.canonical_lab_fenced_writer._root_operation_permit_type",return_value=Bound):
            with self.assertRaisesRegex(FencedWriterRejected,
                                        "FENCE_E_OPERATION_REVOKED"):
                writer(c,a,generation=2).write(record(),content_id=digest(record()))
        self.assertEqual(c.calls,[])

    def test_literal_fence_abi_never_claims_native_or_trade_authority(self):
        details=fenced_writer_abi()
        self.assertEqual(details["sql_function"],"public.lab_fenced_insert")
        self.assertEqual(details["fence_schema"],"lab-postgres-writer-fence.v1")
        self.assertFalse(details["trading_authorized"])
        self.assertTrue(details["lab_only"])
        self.assertEqual(details["native_admission"],"E_ROOT_ISSUED_ONE_USE_OPERATION_PERMIT")


if __name__=="__main__":
    unittest.main()
