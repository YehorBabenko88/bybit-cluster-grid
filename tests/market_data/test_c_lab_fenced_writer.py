"""Negative LAB-only contract checks for Grid's C-owned SQL fence adapter.

The stub is *not* real PostgreSQL. Native PG18 tests must prove actual
SECURITY DEFINER function ownership, revocation and durable high-water.
No network, exchange, DB or service access in this file.
"""
import unittest
import uuid
from types import SimpleNamespace

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


def record():
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


class Admission:
    lab_only=True
    def __init__(self,*values):
        self.values=list(values or [True,True,True])
        self.calls=0
    def require_current(self):
        self.calls+=1
        return self.values.pop(0) if self.values else False


class Connection:
    closed=False
    autocommit=True
    def __init__(self,*,pid=1234,fail_sql=False,fail_commit=False):
        self.pid=pid
        self.fail_sql=fail_sql
        self.fail_commit=fail_commit
        self.calls=[]
        self.rollback_calls=0
    def cursor(self):
        connection=self
        class Cursor:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def execute(self,sql,args=None):
                connection.calls.append((sql,args))
                if connection.fail_sql and "lab_fenced_insert" in sql:
                    raise RuntimeError("DATABASE_FENCE_REJECTED")
            def fetchone(self):return (connection.pid,)
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
    return CanonicalLabMinuteWriter(conn or Connection(),native_admission=auth or Admission(),**args)


class CanonicalLabFencedWriterTests(unittest.TestCase):
    def test_only_exact_sql_security_definer_function_on_same_backend(self):
        c=Connection();a=Admission()
        result=writer(c,a).write(record(),content_id="c"*64)
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
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_NATIVE_ADMISSION_REQUIRED"):
            CanonicalLabMinuteWriter(c,native_admission=None,**VALUES)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_NATIVE_LAB_SCOPE_REQUIRED"):
            writer(c,SimpleNamespace(require_current=lambda:True,lab_only=False))
        self.assertEqual(c.calls,[])

    def test_deny_automatic_transaction_pooled_and_closed_connection(self):
        for diff in ({"autocommit":False},{"closed":True}):
            c=Connection()
            for k,v in diff.items():setattr(c,k,v)
            with self.subTest(diff=diff),self.assertRaises(FencedWriterRejected):
                writer(c)
            self.assertEqual(c.calls,[])

    def test_deny_revoked_before_backend_observation(self):
        c=Connection();a=Admission(False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_NATIVE_ADMISSION_REVOKED"):
            writer(c,a).write(record(),content_id="c"*64)
        self.assertEqual(c.calls,[])

    def test_deny_changed_backend_and_close_unknown_outcome(self):
        c=Connection(pid=5678);w=writer(c)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_BACKEND_CHANGED"):
            w.write(record(),content_id="c"*64)
        self.assertEqual([x[0] for x in c.calls],["BEGIN","SELECT pg_backend_pid()","ROLLBACK"])
        self.assertEqual(c.rollback_calls,1)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_WRITER_ALREADY_USED"):
            w.write(record(),content_id="c"*64)

    def test_revoke_after_backend_check_rolls_back_without_sql(self):
        c=Connection();a=Admission(True,False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_NATIVE_ADMISSION_REVOKED"):
            writer(c,a).write(record(),content_id="c"*64)
        self.assertFalse(any("lab_fenced_insert" in sql for sql,_ in c.calls))
        self.assertEqual(c.calls[-1][0],"ROLLBACK")

    def test_revoke_after_function_before_commit_rolls_back(self):
        c=Connection();a=Admission(True,True,False)
        with self.assertRaisesRegex(FencedWriterRejected,"FENCE_NATIVE_ADMISSION_REVOKED"):
            writer(c,a).write(record(),content_id="c"*64)
        self.assertEqual(len([sql for sql,_ in c.calls if "lab_fenced_insert" in sql]),1)
        self.assertEqual(c.calls[-1][0],"ROLLBACK")

    def test_sql_rejection_and_unknown_commit_are_fatal_no_retry(self):
        for kwargs in ({"fail_sql":True},{"fail_commit":True}):
            c=Connection(**kwargs);w=writer(c)
            with self.subTest(kwargs=kwargs),self.assertRaises(RuntimeError):
                w.write(record(),content_id="c"*64)
            self.assertEqual(len([sql for sql,_ in c.calls if "lab_fenced_insert" in sql]),1)
            with self.assertRaises(FencedWriterRejected):
                w.write(record(),content_id="c"*64)

    def test_invalid_record_and_trading_promotion_never_write(self):
        for modify in ({"producer":"bybit-cluster-grid"},{"execution_authority":True}):
            c=Connection();r=record();r.update(modify)
            r["dataset_fingerprint"]=digest({k:v for k,v in r.items() if k!="dataset_fingerprint"})
            with self.subTest(modify=modify),self.assertRaisesRegex(FencedWriterRejected,"FENCE_MINUTE_NOT_QUALIFIED"):
                writer(c).write(r,content_id="c"*64)
            self.assertEqual(c.calls,[])

    def test_literal_fence_abi_never_claims_native_or_trade_authority(self):
        details=fenced_writer_abi()
        self.assertEqual(details["sql_function"],"public.lab_fenced_insert")
        self.assertEqual(details["fence_schema"],"lab-postgres-writer-fence.v1")
        self.assertFalse(details["trading_authorized"])
        self.assertTrue(details["lab_only"])


if __name__=="__main__":
    unittest.main()
