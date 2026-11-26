"""Synthetic-only B ROUND9 continuity tests. No Bybit, PG, services or trading."""
import asyncio
import unittest
from grid.canonical_lab_continuous_collector import ContinuousLabCollector, CollectorRejected

def minute(ts, c="a"):
    return {"symbol":"BTCUSDT","start_ms":ts,
            "dataset_fingerprint":c*64,"status":"PARTIAL",
            "execution_authority":False,"trading_authorized":False}

class Authority:
    def __init__(self, live=True): self.live=live
    def require_current(self): return self.live

class Journal:
    def __init__(self): self.committed={};self.pending=[];self.outcome="MATCH"
    def read(self,symbol): return self.committed.get(symbol)
    def append_pending(self,m): self.pending.append(m)
    def reconcile(self,m): return self.outcome
    def confirm(self,m):
        if self.outcome!="MATCH": raise RuntimeError("READBACK_MISMATCH")
        self.committed[m.symbol]={"start_ms":m.start_ms,
                                  "fingerprint":m.fingerprint,
                                  "content_id":m.content_id}

class Writer:
    def __init__(self,fail=False): self.fail=fail;self.calls=0
    def write(self,record,*,content_id):
        self.calls+=1
        if self.fail: raise RuntimeError("UNKNOWN_COMMIT")
        return {"status":"LOCAL_COMMIT_RETURNED",
                "fingerprint":record["dataset_fingerprint"],
                "execution_authority":False,"trading_authorized":False}

class Transport:
    def __init__(self,items=None): self.items=items or [];self.calls=[]
    async def backfill(self,symbol,start,end,limit):
        self.calls.append((symbol,start,end,limit))
        return self.items

class CoordinatorTests(unittest.TestCase):
    def setup(self,writer=None,transport=None,journal=None,authority=None,**kw):
        j=journal or Journal()
        w=writer or Writer()
        a=authority or Authority()
        t=transport or Transport()
        return ContinuousLabCollector(transport=t,writer_factory=lambda _:w,
            journal=j,authority=a,**kw),j,w,a,t

    def test_single_writer_no_parallel_transport_or_trade(self):
        c,j,w,a,t=self.setup();c.begin()
        self.assertEqual(c.deliver(minute(60000),content_id="1"*64),"COMMITTED")
        self.assertEqual(w.calls,1)
        self.assertEqual(j.committed["BTCUSDT"]["start_ms"],60000)
        self.assertFalse(c.diagnostic()["trading_authorized"])
        self.assertFalse(c.diagnostic()["native_admitted"])

    def test_dedup_cannot_reinsert(self):
        c,j,w,a,t=self.setup();c.begin()
        r=minute(60000)
        self.assertEqual(c.deliver(r,content_id="1"*64),"COMMITTED")
        self.assertEqual(c.deliver(r,content_id="1"*64),"DEDUP")
        self.assertEqual(w.calls,1)

    def test_conflict_stale_and_wrong_fingerprint_halt(self):
        c,j,w,a,t=self.setup();c.begin()
        c.deliver(minute(60000),content_id="1"*64)
        with self.assertRaisesRegex(CollectorRejected,"CONFLICT_OR_OLD_MINUTE"):
            c.deliver(minute(60000,"b"),content_id="2"*64)
        self.assertEqual(c.state,"HALTED")

    def test_gap_requires_bounded_canonical_transport(self):
        items=[(minute(120000), "2"*64), (minute(180000),"3"*64)]
        c,j,w,a,t=self.setup(transport=Transport(items));c.begin()
        c.deliver(minute(60000),content_id="1"*64)
        self.assertEqual(c.deliver(minute(240000),content_id="4"*64),"GAP")
        self.assertEqual(asyncio.run(c.recover_gap()),"COMMITTED")
        self.assertEqual(t.calls,[("BTCUSDT",120000,180000,256)])
        self.assertEqual(j.committed["BTCUSDT"]["start_ms"],240000)
        self.assertEqual(w.calls,4)

    def test_gap_fails_closed_when_truncated(self):
        c,j,w,a,t=self.setup(transport=Transport([]));c.begin()
        c.deliver(minute(60000),content_id="1"*64)
        c.deliver(minute(180000),content_id="3"*64)
        with self.assertRaisesRegex(CollectorRejected,"BACKFILL_INCOMPLETE"):
            asyncio.run(c.recover_gap())
        self.assertNotEqual(c.state,"READY")

    def test_unknown_commit_does_not_blind_retry(self):
        c,j,w,a,t=self.setup(writer=Writer(fail=True));c.begin()
        with self.assertRaisesRegex(RuntimeError,"UNKNOWN_COMMIT"):
            c.deliver(minute(60000),content_id="1"*64)
        self.assertEqual(c.state,"HALTED")
        self.assertEqual(w.calls,1)
        with self.assertRaisesRegex(CollectorRejected,"UNKNOWN_COMMIT_UNRESOLVED"):
            c.reconcile_after_restart(new_authority=Authority())
        self.assertEqual(w.calls,1)
        j.outcome="MATCH"
        self.assertEqual(c.reconcile_after_restart(new_authority=Authority()),
                         "RECONCILED")
        self.assertEqual(w.calls,1)

    def test_lease_revocation_halts(self):
        c,j,w,a,t=self.setup();c.begin();a.live=False
        with self.assertRaisesRegex(CollectorRejected,"AUTHORITY_REVOKED"):
            c.deliver(minute(60000),content_id="1"*64)
        self.assertEqual(w.calls,0)

    def test_writer_receipt_mismatch_does_not_advance(self):
        class BadWriter:
            def write(self,*args,**kwargs):
                return {"status":"LOCAL_COMMIT_RETURNED","fingerprint":"b"*64,
                        "execution_authority":False,"trading_authorized":False}
        c,j,w,a,t=self.setup(writer=BadWriter());c.begin()
        with self.assertRaisesRegex(CollectorRejected,"WRITE_RECEIPT_UNQUALIFIED"):
            c.deliver(minute(60000),content_id="1"*64)
        self.assertNotIn("BTCUSDT",j.committed)
        self.assertEqual(c.state,"HALTED")

    def test_readback_mismatch_halts_and_preserves_pending(self):
        j=Journal();j.outcome="UNKNOWN"
        c,j,w,a,t=self.setup(journal=j);c.begin()
        with self.assertRaisesRegex(CollectorRejected,"READBACK_NOT_PROVEN"):
            c.deliver(minute(60000),content_id="1"*64)
        self.assertIsNotNone(c.pending)
        self.assertNotIn("BTCUSDT",j.committed)

    def test_backfill_rejects_noncontiguous(self):
        c,j,w,a,t=self.setup(transport=Transport([(minute(180000),"3"*64)]))
        c.begin();c.deliver(minute(60000),content_id="1"*64)
        c.deliver(minute(180000),content_id="3"*64)
        with self.assertRaisesRegex(CollectorRejected,"BACKFILL_NOT_CONTIGUOUS"):
            asyncio.run(c.recover_gap())
        self.assertEqual(w.calls,1)

    def test_no_forgeable_missing_root_components(self):
        with self.assertRaisesRegex(CollectorRejected,"AUTHORITY_REQUIRED"):
            ContinuousLabCollector(transport=Transport(),writer_factory=lambda _:Writer(),
                                   journal=Journal(),authority=None)
        c,j,w,a,t=self.setup();self.assertEqual(c.state,"STOPPED")
        with self.assertRaisesRegex(CollectorRejected,"COLLECTOR_NOT_READY"):
            c.deliver(minute(60000),content_id="1"*64)

if __name__=="__main__":
    unittest.main()
