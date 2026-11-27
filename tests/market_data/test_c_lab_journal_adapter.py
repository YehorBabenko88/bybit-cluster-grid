"""B Round11 isolated C ABI regression; no PostgreSQL or native Root grant.

A small *synthetic* E executor class is installed only in this test module,
never in the runtime. Real Root bounded-thread/heartbeat proof is E-owned.
"""
import asyncio
import sys
import types
import unittest
from types import SimpleNamespace

from grid.c_lab_journal_adapter import COwnedLabJournal
from grid.canonical_lab_continuous_collector import CollectorRejected

KEY=dict(symbol="BTCUSDT",start_ms=60000,fingerprint="a"*64,content_id="b"*64)
IDENTITY=SimpleNamespace(source_sha256="c"*64,schema_sha256="d"*64)

class C:
    def __init__(self):
        self.calls=[]
        self.pending_value=None
        self.cursor_value=None
        self.state="EXACT_ALREADY_ACKNOWLEDGED"
        self.readback_status="MATCH"
    def _record(self,name,**kw):
        self.calls.append((name,kw))
    def read_lab_pending(self,pg,*,stream_id):
        self._record("pending",stream_id=stream_id)
        return self.pending_value
    def read_lab_checkpoint(self,pg,*,stream_id):
        self._record("checkpoint",stream_id=stream_id)
        return self.cursor_value
    def append_lab_pending(self,pg,**kw):
        self._record("append",**kw)
        return {"schema":"lab-pg-pending-append.v1",
                "stream_id":kw["stream_id"],"native_admitted":False}
    def read_committed_lab_minute(self,pg,**kw):
        self._record("readback",**kw)
        return {"schema":"lab-pg-committed-readback.v1",
                "status":self.readback_status,"native_admitted":False,
                **{k:kw[k] for k in KEY}}
    def commit_verified_lab_cursor(self,pg,**kw):
        self._record("cas",**kw)
        return {"schema":"lab-pg-durable-cursor.v1",
                "cursor":kw["cursor"],"fingerprint":kw["fingerprint"],
                "content_id":kw["content_id"],
                "committed_record_verified":True,"native_admitted":False}
    def verify_existing_lab_checkpoint(self,pg,**kw):
        self._record("existing",**kw)
        return {"schema":"lab-pg-exact-checkpoint-reconciliation.v1",
                "state":self.state,"native_admitted":False,
                **{k:kw[k] for k in KEY}}
    def clear_verified_lab_pending(self,pg,**kw):
        self._record("clear",**kw)
        return True

class CAdapterTests(unittest.TestCase):
    def setUp(self):
        package=types.ModuleType("unified_system");package.__path__=[]
        ex=types.ModuleType("unified_system.lab_owner_executor")
        class LabOwnerExecutor:
            def __init__(self):self.calls=0;self.fail=False
            async def call(self,op,*,timeout=10.0):
                self.calls+=1
                if self.fail:raise TimeoutError("SYNTHETIC_TIMEOUT")
                return op()
        ex.LabOwnerExecutor=LabOwnerExecutor
        self.executor_type=LabOwnerExecutor
        self.old_package=sys.modules.get("unified_system")
        self.old_executor=sys.modules.get("unified_system.lab_owner_executor")
        sys.modules["unified_system"]=package
        sys.modules["unified_system.lab_owner_executor"]=ex
    def tearDown(self):
        for key,old in (("unified_system",self.old_package),
            ("unified_system.lab_owner_executor",self.old_executor)):
            if old is None:sys.modules.pop(key,None)
            else:sys.modules[key]=old
    def make(self):
        c=C()
        ex=self.executor_type()
        journal=COwnedLabJournal(c_module=c,pg=object(),identity=IDENTITY,
              generation=2,backend_pid=1234,stream_id="grid/BTCUSDT/1m",
              owner_executor=ex)
        return journal,c,ex

    def test_pending_from_c_restored_by_exact_identity(self):
        j,c,e=self.make()
        c.pending_value=dict(KEY,generation=1,token=42,
                             source_sha256=IDENTITY.source_sha256,
                             schema_sha256=IDENTITY.schema_sha256)
        self.assertEqual(asyncio.run(j.pending())["content_id"],KEY["content_id"])
        self.assertEqual(c.calls[0][0],"pending")
        self.assertEqual(e.calls,1)
    def test_foreign_source_pending_refused(self):
        j,c,e=self.make()
        c.pending_value=dict(KEY,generation=1,token=42,
                             source_sha256="e"*64,
                             schema_sha256=IDENTITY.schema_sha256)
        with self.assertRaisesRegex(CollectorRejected,"C_PENDING_SOURCE_OR_OWNER_CHANGED"):
            asyncio.run(j.pending())
    def test_c_exact_readback_and_cas(self):
        j,c,e=self.make()
        self.assertEqual(asyncio.run(j.readback(KEY))["status"],"MATCH")
        self.assertEqual(asyncio.run(j.commit_cursor(KEY))["cursor"],60000)
        self.assertEqual(c.calls[1][1]["generation"],2)
        self.assertEqual(c.calls[1][1]["backend_pid"],1234)
        self.assertEqual(c.calls[1][1]["cursor"],60000)
    def test_missing_is_never_acknowledged(self):
        j,c,e=self.make()
        c.readback_status="MISSING"
        self.assertEqual(asyncio.run(j.readback(KEY))["status"],"MISSING")
        self.assertFalse(any(x[0]=="cas" for x in c.calls))
    def test_exact_existing_checkpoint_read_only(self):
        j,c,e=self.make()
        r=asyncio.run(j.exact_existing_checkpoint(KEY))
        self.assertEqual(r["state"],"EXACT_ALREADY_ACKNOWLEDGED")
        self.assertFalse(any(x[0]=="cas" for x in c.calls))
    def test_ambiguous_ack_not_promoted(self):
        j,c,e=self.make();c.state="UNRESOLVED"
        self.assertEqual(asyncio.run(j.exact_existing_checkpoint(KEY))["state"],"UNRESOLVED")
        with self.assertRaisesRegex(CollectorRejected,"C_PENDING_CLEAR_REQUIRES_EXACT_CHECKPOINT"):
            asyncio.run(j.clear_pending(KEY))
        self.assertFalse(any(x[0] in ("cas","clear") for x in c.calls))
    def test_clear_requires_exact_c_confirmation(self):
        j,c,e=self.make()
        self.assertTrue(asyncio.run(j.clear_pending(KEY)))
        self.assertEqual([x[0] for x in c.calls],["existing","clear"])
        self.assertEqual(c.calls[-1][1]["generation"],2)
        self.assertEqual(c.calls[-1][1]["backend_pid"],1234)
    def test_wrong_symbol_in_c_receipt_is_rejected(self):
        j,c,e=self.make()
        original=c.verify_existing_lab_checkpoint
        def bad(pg,**kw):
            r=original(pg,**kw);r["symbol"]="ETHUSDT";return r
        c.verify_existing_lab_checkpoint=bad
        with self.assertRaisesRegex(CollectorRejected,"C_EXISTING_CURSOR_IDENTITY_MISMATCH"):
            asyncio.run(j.exact_existing_checkpoint(KEY))
    def test_missing_symbol_in_c_receipt_is_rejected(self):
        j,c,e=self.make()
        original=c.verify_existing_lab_checkpoint
        def bad(pg,**kw):
            r=original(pg,**kw);r.pop("symbol");return r
        c.verify_existing_lab_checkpoint=bad
        with self.assertRaisesRegex(CollectorRejected,"C_EXISTING_CURSOR_IDENTITY_MISMATCH"):
            asyncio.run(j.exact_existing_checkpoint(KEY))
    def test_executor_timeout_poisoning_requires_fresh_owner(self):
        j,c,e=self.make()
        e.fail=True
        with self.assertRaises(TimeoutError):
            asyncio.run(j.pending())
        e.fail=False
        with self.assertRaisesRegex(CollectorRejected,"C_OWNER_SESSION_UNCERTAIN"):
            asyncio.run(j.pending())
        self.assertEqual(e.calls,1)
    def test_no_root_executor_not_accepted(self):
        c=C()
        with self.assertRaisesRegex(CollectorRejected,"ROOT_BOUNDED_C_EXECUTOR_REQUIRED"):
            COwnedLabJournal(c_module=c,pg=object(),identity=IDENTITY,
              generation=2,backend_pid=1234,stream_id="grid/BTCUSDT/1m",
              owner_executor=object())
    def test_no_independent_writer_or_grant(self):
        j,c,e=self.make()
        self.assertFalse(hasattr(j,"issue_authority"))
        self.assertFalse(hasattr(j,"connect"))
        self.assertFalse(hasattr(j,"insert"))

if __name__=="__main__":unittest.main()
