"""Synthetic-only proof of B async scheduling around the EXACT one-shot writer.

No live PostgreSQL, authentication issuance or Bybit. E's executor class is
shimmed only in this test process; native E thread/PG tests are separate.
"""
import asyncio
import sys
import types
import unittest

from grid.canonical_lab_fenced_writer import CanonicalLabMinuteWriter
from market_data.provenance import minute_record, producer, digest
from grid.c_async_fenced_writer import AsyncCanonicalFencedWriter
from grid.canonical_lab_continuous_collector import CollectorRejected

def record():
    src=producer("fixture","a"*40,"wss://stream.bybit.com/v5/public/linear")
    row={"symbol":"BTCUSDT","start_ms":60000,
         "source_event_start_ms":60001,"source_event_end_ms":119999,
         "source_provenance":src,
         "open":1.0,"high":2.0,"low":1.0,"close":2.0,
         "buy_volume":1.0,"sell_volume":0.0,"delta":1.0,
         "trade_count":1,"poc_price":2.0,"quality_status":"GOOD",
         "quality_reasons":[],
         "levels":[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
                    "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}]}
    return minute_record(row,120000,"fixture")

class Tests(unittest.TestCase):
    def setUp(self):
        package=types.ModuleType("unified_system");package.__path__=[]
        sub=types.ModuleType("unified_system.lab_owner_executor")
        class LabOwnerExecutor:
            def __init__(self):self.calls=0;self.fail=None
            async def call(self,fn,*,timeout):
                self.calls+=1
                if self.fail is not None:raise self.fail
                return fn()
        sub.LabOwnerExecutor=LabOwnerExecutor
        self.cls=LabOwnerExecutor
        self.oldp=sys.modules.get("unified_system")
        self.olde=sys.modules.get("unified_system.lab_owner_executor")
        sys.modules["unified_system"]=package
        sys.modules["unified_system.lab_owner_executor"]=sub
    def tearDown(self):
        for name,old in (("unified_system",self.oldp),
                         ("unified_system.lab_owner_executor",self.olde)):
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
    def setup_writer(self,*,receipt=None,raised=None):
        raw=object.__new__(CanonicalLabMinuteWriter)
        calls=[]
        def write(record,*,content_id):
            calls.append((record,content_id))
            if raised is not None:raise raised
            return (receipt if receipt is not None else {
                    "schema":"market-data.c-fenced-write-result.v1",
                    "status":"LOCAL_COMMIT_RETURNED",
                    "fingerprint":record()["dataset_fingerprint"],
                    "content_id":content_id,
                    "execution_authority":False,
                    "trading_authorized":False})
        raw.write=write
        owner=self.cls()
        return AsyncCanonicalFencedWriter(writer=raw,owner_executor=owner),calls,owner

    def test_only_exact_writer_uses_single_root_executor(self):
        writer,calls,owner=self.setup_writer()
        item=record()
        got=asyncio.run(writer.write(item,content_id=digest(item)))
        self.assertEqual(got["status"],"LOCAL_COMMIT_RETURNED")
        self.assertEqual(len(calls),1)
        self.assertEqual(owner.calls,1)
        with self.assertRaisesRegex(CollectorRejected,"ALREADY_USED_OR_UNCERTAIN"):
            asyncio.run(writer.write({},content_id="b"*64))
        self.assertEqual(len(calls),1)

    def test_unknown_commit_does_not_retry(self):
        writer,calls,owner=self.setup_writer(raised=TimeoutError("ACK_UNKNOWN"))
        with self.assertRaises(TimeoutError):
            asyncio.run(writer.write(record(),content_id=digest(record())))
        with self.assertRaisesRegex(CollectorRejected,"ALREADY_USED_OR_UNCERTAIN"):
            asyncio.run(writer.write(record(),content_id=digest(record())))
        self.assertEqual(len(calls),1)
        self.assertEqual(owner.calls,1)

    def test_cancellation_is_not_a_retryable_failure(self):
        writer,calls,owner=self.setup_writer()
        owner.fail=asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(writer.write(record(),content_id=digest(record())))
        self.assertEqual(owner.calls,1)
        with self.assertRaises(CollectorRejected):
            asyncio.run(writer.write(record(),content_id=digest(record())))
        self.assertEqual(len(calls),0)

    def test_unqualified_receipt_fail_closed(self):
        writer,calls,owner=self.setup_writer(receipt={
            "schema":"market-data.c-fenced-write-result.v1",
            "status":"LOCAL_COMMIT_RETURNED",
            "execution_authority":True,"trading_authorized":False})
        with self.assertRaisesRegex(CollectorRejected,"RECEIPT_UNQUALIFIED"):
            asyncio.run(writer.write(record(),content_id=digest(record())))
        self.assertEqual(owner.calls,1)
        with self.assertRaises(CollectorRejected):
            asyncio.run(writer.write(record(),content_id=digest(record())))

    def test_forged_canonical_content_id_denied_before_owner_executor(self):
        writer,calls,owner=self.setup_writer()
        with self.assertRaisesRegex(CollectorRejected,"CANONICAL_CONTENT_ID_REQUIRED"):
            asyncio.run(writer.write(record(),content_id="0"*64))
        self.assertEqual(owner.calls,0)
        self.assertEqual(calls,[])

    def test_raw_sql_connection_and_fake_writer_rejected(self):
        with self.assertRaisesRegex(CollectorRejected,"EXACT_C_FENCED_WRITER_REQUIRED"):
            AsyncCanonicalFencedWriter(writer=object(),owner_executor=self.cls())
        raw=object.__new__(CanonicalLabMinuteWriter)
        with self.assertRaisesRegex(CollectorRejected,"ROOT_SERIAL_WRITER_EXECUTOR_REQUIRED"):
            AsyncCanonicalFencedWriter(writer=raw,owner_executor=object())

if __name__=="__main__":unittest.main()
