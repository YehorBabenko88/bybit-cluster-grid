"""Pure B LAB contract regression for exact C-owned checkpoint facade.

Mocks only C's owner-call ABI, with no PostgreSQL execution or native grant.
The facade is non-actuating until E/Root admit a genuinely protected cohort.
"""
import unittest
import asyncio
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
                "status":self.readback_status,"native_admitted":False,**{
                    k:kw[k] for k in KEY}}
    def commit_verified_lab_cursor(self,pg,**kw):
        self._record("cas",**kw)
        return {"schema":"lab-pg-durable-cursor.v1",
                "cursor":kw["cursor"],"fingerprint":kw["fingerprint"],
                "content_id":kw["content_id"],
                "committed_record_verified":True,"native_admitted":False}
    def verify_existing_lab_checkpoint(self,pg,**kw):
        self._record("existing",**kw)
        return {"schema":"lab-pg-exact-checkpoint-reconciliation.v1",
                "state":self.state,"native_admitted":False,**{
                    k:kw[k] for k in KEY}}
    def clear_verified_lab_pending(self,pg,**kw):
        self._record("clear",**kw)
        return True

class CAdapterTests(unittest.TestCase):
    def make(self):
        c=C()
        journal=COwnedLabJournal(c_module=c,pg=object(),identity=IDENTITY,
              generation=2,backend_pid=1234,stream_id="grid/BTCUSDT/1m")
        return journal,c
    def test_pending_from_c_restored_by_exact_identity(self):
        j,c=self.make()
        c.pending_value=dict(KEY,generation=1,token=42,
                             source_sha256=IDENTITY.source_sha256,
                             schema_sha256=IDENTITY.schema_sha256)
        self.assertEqual(asyncio.run(j.pending())["content_id"],KEY["content_id"])
        self.assertEqual(c.calls[0][0],"pending")
    def test_foreign_source_pending_refused(self):
        j,c=self.make()
        c.pending_value=dict(KEY,generation=1,token=42,
                             source_sha256="e"*64,
                             schema_sha256=IDENTITY.schema_sha256)
        with self.assertRaisesRegex(CollectorRejected,"C_PENDING_SOURCE_OR_OWNER_CHANGED"):
            asyncio.run(j.pending())
    def test_c_exact_readback_and_cas(self):
        j,c=self.make()
        self.assertEqual(asyncio.run(j.readback(KEY))["status"],"MATCH")
        self.assertEqual(asyncio.run(j.commit_cursor(KEY))["cursor"],60000)
        self.assertEqual(c.calls[1][1]["generation"],2)
        self.assertEqual(c.calls[1][1]["backend_pid"],1234)
        self.assertEqual(c.calls[1][1]["cursor"],60000)
    def test_missing_is_never_acknowledged(self):
        j,c=self.make()
        c.readback_status="MISSING"
        self.assertEqual(asyncio.run(j.readback(KEY))["status"],"MISSING")
        self.assertFalse(any(x[0]=="cas" for x in c.calls))
    def test_exact_existing_checkpoint_read_only(self):
        j,c=self.make()
        receipt=asyncio.run(j.exact_existing_checkpoint(KEY))
        self.assertEqual(receipt["state"],"EXACT_ALREADY_ACKNOWLEDGED")
        self.assertFalse(any(x[0]=="cas" for x in c.calls))
    def test_ambiguous_ack_not_promoted(self):
        j,c=self.make()
        c.state="UNRESOLVED"
        self.assertEqual(asyncio.run(j.exact_existing_checkpoint(KEY))["state"],"UNRESOLVED")
        self.assertFalse(any(x[0] in ("cas","clear") for x in c.calls))
    def test_clear_requires_c_owner_confirmation(self):
        j,c=self.make()
        self.assertTrue(asyncio.run(j.clear_pending(KEY)))
        self.assertEqual(c.calls[-1][0],"clear")
        self.assertEqual(c.calls[-1][1]["generation"],2)
        self.assertEqual(c.calls[-1][1]["backend_pid"],1234)
    def test_sync_c_does_not_bypass_native(self):
        j,c=self.make()
        self.assertFalse(hasattr(j,"issue_authority"))
        self.assertFalse(hasattr(j,"connect"))
        self.assertFalse(hasattr(j,"insert"))
if __name__=="__main__":unittest.main()
