"""SYNTHETIC B state-machine fault tests, not native Root/E/C authorization.

Only a local test-side E module is substituted to exercise the otherwise
unreachable, sealed-grant branch. Never use these fixtures as LAB permission,
PG18 E2E, provider authenticity, or 24h acceptance evidence.
"""
import asyncio
import dataclasses
import sys
import types
import unittest
from market_data.provenance import minute_record,producer
from grid.canonical_lab_continuous_collector import ContinuousLabCollector,CollectorRejected

NOW=1800000600000
BASE=(NOW//60000-10)*60000
SRC=producer("fixture","a"*40,"wss://stream.bybit.com/v5/public/linear")

def record(start):
    row={"symbol":"BTCUSDT","start_ms":start,
         "source_event_start_ms":start+1,"source_event_end_ms":start+59000,
         "source_provenance":SRC,"open":1.0,"high":2.0,
         "low":1.0,"close":2.0,"buy_volume":1.0,"sell_volume":0.0,
         "delta":1.0,"trade_count":1,"poc_price":2.0,
         "levels":[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
                    "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}],
         "quality_status":"GOOD","quality_reasons":[]}
    return minute_record(row,NOW,"fixture")
def cid(i):return ("%064x"%i)

class Journal:
    def __init__(self):
        self.cursor=None
        self.outstanding=None
        self.written={}
        self.cas_calls=0
        self.clear_calls=0
        self.lose_cas_ack=False
        self.lose_clear_ack=False
    async def checkpoint(self):return self.cursor
    async def pending(self):return self.outstanding
    async def append_pending(self,m):
        if self.outstanding is not None:raise RuntimeError("MULTIPLE_PENDING")
        self.outstanding=dict(symbol=m.symbol,start_ms=m.start_ms,
                              fingerprint=m.fingerprint,content_id=m.content_id,
                              generation=1,token=2,source_sha256="c"*64,
                              schema_sha256="d"*64)
    async def readback(self,m):
        key=(m.symbol,m.start_ms,m.fingerprint,m.content_id)
        return {"status":"MATCH" if key in self.written else "MISSING"}
    async def commit_cursor(self,m):
        self.cas_calls+=1
        if self.cursor is not None and m.start_ms!=self.cursor["start_ms"]+60000:
            raise RuntimeError("C_CURSOR_CAS_DENIED")
        self.cursor=dict(symbol=m.symbol,start_ms=m.start_ms,
                         fingerprint=m.fingerprint,content_id=m.content_id)
        if self.lose_cas_ack:
            self.lose_cas_ack=False
            raise TimeoutError("LOST_CURSOR_ACK")
        return {"schema":"lab-pg-durable-cursor.v1","cursor":m.start_ms}
    async def exact_existing_checkpoint(self,m):
        target=(m.symbol,m.start_ms,m.fingerprint,m.content_id)
        exact=self.cursor is not None and target==tuple(self.cursor[k] for k in
                 ("symbol","start_ms","fingerprint","content_id"))
        pending=self.outstanding is not None and target==tuple(self.outstanding[k] for k in
                 ("symbol","start_ms","fingerprint","content_id"))
        return {"state":"EXACT_ALREADY_ACKNOWLEDGED" if exact and pending else "UNRESOLVED"}
    async def clear_pending(self,m):
        self.clear_calls+=1
        if (await self.exact_existing_checkpoint(m))["state"]!="EXACT_ALREADY_ACKNOWLEDGED":
            raise RuntimeError("C_PENDING_CLEAR_DENIED")
        self.outstanding=None
        if self.lose_clear_ack:
            self.lose_clear_ack=False
            raise TimeoutError("LOST_CLEAR_ACK")
        return True

class Writer:
    def __init__(self,j,m,mode):self.j=j;self.m=m;self.mode=mode
    async def write(self,record,*,content_id):
        key=(self.m.symbol,self.m.start_ms,self.m.fingerprint,content_id)
        if key in self.j.written:raise RuntimeError("UNIQUE_KEY_NOT_ACK")
        self.j.written[key]=record
        if self.mode=="lost_write_ack":raise TimeoutError("UNKNOWN_COMMIT")
        if self.mode=="cancel_write":raise asyncio.CancelledError()
        return {"status":"LOCAL_COMMIT_RETURNED",
                "fingerprint":self.m.fingerprint,
                "trading_authorized":False}

class Factory:
    def __init__(self,j):self.j=j;self.mode=None;self.calls=0
    async def __call__(self,m):
        self.calls+=1
        return Writer(self.j,m,self.mode)

class Transport:
    def __init__(self):self.pages=[];self.calls=[]
    async def backfill(self,symbol,start,end,limit):
        self.calls.append((symbol,start,end,limit))
        return self.pages

class Tests(unittest.TestCase):
    def setUp(self):
        m=types.ModuleType("unified_system.lab_writer_authority")
        p=types.ModuleType("unified_system");p.__path__=[]
        @dataclasses.dataclass(frozen=True)
        class LabAuthorityStatus:
            schema:str;scope:str;epoch:str;generation:int;state:str
            native_admitted:bool=False;trading_authorized:bool=False
        class LabWriterGrant:
            def __init__(self,epoch):self.epoch=epoch
            async def require_write_current(self):return self
        m.LabAuthorityStatus=LabAuthorityStatus
        m.LabWriterGrant=LabWriterGrant
        self.oldp=sys.modules.get("unified_system")
        self.oldm=sys.modules.get("unified_system.lab_writer_authority")
        sys.modules["unified_system"]=p
        sys.modules["unified_system.lab_writer_authority"]=m
        self.S=LabAuthorityStatus;self.Grant=LabWriterGrant
        self.j=Journal();self.factory=Factory(self.j);self.transport=Transport()
        self.authority=self._authority()
    def tearDown(self):
        for name,old in (("unified_system",self.oldp),
                         ("unified_system.lab_writer_authority",self.oldm)):
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
    def _authority(self,epoch="a"*64,generation=1):
        s=self.S("unified.lab-root-writer-authority.v1",
                 "ISOLATED_LAB_ONLY",epoch,generation,
                 "READ_ONLY_REVALIDATED_NOT_NATIVE")
        return types.SimpleNamespace(check=lambda: self._check(s))
    async def _check(self,status):return status
    def collector(self,epoch="a"*64,generation=1):
        return ContinuousLabCollector(transport=self.transport,
            writer_factory=self.factory,journal=self.j,
            authority=self._authority(epoch,generation),
            writer_grant=self.Grant(epoch))
    def test_one_minute_commit_and_dedup(self):
        async def run():
            c=self.collector();await c.begin()
            self.assertEqual(await c.deliver(record(BASE),content_id=cid(1)),"COMMITTED")
            self.assertEqual(await c.deliver(record(BASE),content_id=cid(1)),"DEDUP")
            self.assertEqual(self.factory.calls,1)
            self.assertEqual(self.j.cas_calls,1)
            self.assertEqual(self.j.clear_calls,1)
        asyncio.run(run())
    def test_conflict_is_not_dedup(self):
        async def run():
            c=self.collector();await c.begin()
            await c.deliver(record(BASE),content_id=cid(1))
            with self.assertRaisesRegex(CollectorRejected,"CONFLICT_OR_OLD_MINUTE"):
                await c.deliver(record(BASE),content_id=cid(2))
            self.assertEqual(c.state,"HALTED")
        asyncio.run(run())
    def test_gap_bounded_backfill_and_tail(self):
        async def run():
            c=self.collector();await c.begin()
            await c.deliver(record(BASE),content_id=cid(1))
            self.assertEqual(await c.deliver(record(BASE+180000),content_id=cid(4)),"GAP")
            self.transport.pages=[(record(BASE+60000),cid(2)),(record(BASE+120000),cid(3))]
            self.assertEqual(await c.recover_gap(),"COMMITTED")
            self.assertEqual(self.j.cursor["start_ms"],BASE+180000)
            self.assertEqual(self.factory.calls,4)
            self.assertEqual(c.state,"READY")
        asyncio.run(run())
    def test_short_backfill_leaves_tail_and_retry(self):
        async def run():
            c=self.collector()
            await c.begin()
            await c.deliver(record(BASE),content_id=cid(1))
            await c.deliver(record(BASE+180000),content_id=cid(4))
            self.transport.pages=[(record(BASE+60000),cid(2))]
            with self.assertRaisesRegex(CollectorRejected,"BACKFILL_INCOMPLETE"):
                await c.recover_gap()
            self.assertEqual(c.tail.start_ms,BASE+180000)
            self.assertEqual(self.j.cursor["start_ms"],BASE)
            self.transport.pages=[(record(BASE+60000),cid(2)),(record(BASE+120000),cid(3))]
            self.assertEqual(await c.recover_gap(),"COMMITTED")
        asyncio.run(run())
    def test_unknown_commit_recovers_from_fresh_process_without_rewrite(self):
        async def run():
            c=self.collector();await c.begin()
            self.factory.mode="lost_write_ack"
            with self.assertRaises(TimeoutError):
                await c.deliver(record(BASE),content_id=cid(1))
            self.assertEqual(c.state,"HALTED")
            self.assertIsNotNone(self.j.outstanding)
            self.factory.mode=None
            fresh=self.collector(epoch="b"*64,generation=2)
            self.assertEqual(await fresh.begin(),"RECOVERY_REQUIRED")
            self.assertEqual(await fresh.reconcile_after_restart(
                fresh_authority=self._authority("b"*64,2),
                fresh_grant=self.Grant("b"*64)),"RECOVERED_BY_EXACT_ROW")
            self.assertEqual(self.factory.calls,1)
            self.assertIsNone(self.j.outstanding)
        asyncio.run(run())
    def test_lost_cas_ack_uses_exact_existing_without_repeating_cas(self):
        async def run():
            c=self.collector();await c.begin()
            self.j.lose_cas_ack=True
            with self.assertRaises(TimeoutError):
                await c.deliver(record(BASE),content_id=cid(1))
            self.assertEqual(self.j.cas_calls,1)
            fresh=self.collector(epoch="b"*64)
            await fresh.begin()
            self.assertEqual(await fresh.reconcile_after_restart(
                fresh_authority=self._authority("b"*64),
                fresh_grant=self.Grant("b"*64)),"CURSOR_ALREADY_ACKNOWLEDGED")
            self.assertEqual(self.j.cas_calls,1)
            self.assertEqual(self.factory.calls,1)
        asyncio.run(run())
    def test_lost_clear_ack_no_blind_replay(self):
        async def run():
            c=self.collector();await c.begin()
            self.j.lose_clear_ack=True
            with self.assertRaises(TimeoutError):
                await c.deliver(record(BASE),content_id=cid(1))
            self.assertIsNone(self.j.outstanding)
            fresh=self.collector(epoch="b"*64)
            self.assertEqual(await fresh.begin(),"READ_ONLY_READY")
            self.assertEqual(self.factory.calls,1)
        asyncio.run(run())
    def test_pump_uses_existing_grid_feed_sequentially(self):
        async def feed():
            for i in range(3):
                yield (record(BASE+i*60000),cid(i+1))
        async def run():
            c=self.collector();await c.begin()
            result=await c.pump_existing_grid_feed(feed(),max_items=3)
            self.assertEqual(result["processed_candidates"],3)
            self.assertFalse(result["trading_authorized"])
            self.assertEqual(self.j.cursor["start_ms"],BASE+120000)
            self.assertEqual(self.factory.calls,3)
            self.assertEqual(c.state,"READY")
        asyncio.run(run())
    def test_cancel_write_halts_with_pending(self):
        async def run():
            c=self.collector();await c.begin()
            self.factory.mode="cancel_write"
            with self.assertRaises(asyncio.CancelledError):
                await c.deliver(record(BASE),content_id=cid(1))
            self.assertEqual(c.state,"HALTED")
            self.assertIsNotNone(self.j.outstanding)
        asyncio.run(run())

if __name__=="__main__":unittest.main()
