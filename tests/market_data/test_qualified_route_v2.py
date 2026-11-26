"""Root-admitted Market Data v2 route: inert synthetic producer->reader->HTTP tests."""
import copy
import time
import unittest
import uuid
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from market_data.provenance import minute_record, producer, digest
from market_data_v2.read_api import Handler, ROUTE, qualified_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError

NOW=1800000120000
START=(NOW//60000-1)*60000


def canonical_fixture():
    source=producer("root-admitted-fixture","a"*40,"wss://stream.bybit.com/v5/public/linear")
    row={
        "symbol":"BTCUSDT","start_ms":START,
        "source_event_start_ms":START+1,
        "source_event_end_ms":START+59000,
        "source_provenance":source,"open":1.0,"high":2.0,
        "low":1.0,"close":2.0,"buy_volume":1.0,
        "sell_volume":0.0,"delta":1.0,"trade_count":1,"poc_price":2.0,
        "quality_status":"GOOD","quality_reasons":[],
        "levels":[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
                   "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}]}
    return minute_record(row,NOW,"root-admitted-fixture")


class Admission:
    def __init__(self, values=(True,)):
        self.values=list(values)
        self.calls=0
    def require_current(self):
        self.calls+=1
        return self.values.pop(0) if self.values else False


def fake_handler(*,token="b"*64,identity=True,admission=None,path=None):
    handler=object.__new__(Handler)
    handler.server=SimpleNamespace(
        module_identity={"instance_token":"b"*64} if identity else None,
        startup_admission=admission if admission is not None else Admission((True,True,True)))
    handler.headers=Message()
    if token is not None:
        handler.headers.add_header("Authorization","Bearer "+token)
    handler.path=path if path is not None else ROUTE+"?symbol=BTCUSDT&limit=1"
    handler.out=[]
    handler._json=lambda status,body:handler.out.append((status,body))
    return handler


class QualifiedReadRouteTests(unittest.TestCase):
    def test_actual_canonical_producer_through_read_only_v2_envelope(self):
        record=canonical_fixture();requests=[]
        def reader(symbol,limit,before):
            requests.append((symbol,limit,before));return [copy.deepcopy(record)]
        out=qualified_snapshot("BTCUSDT",1,reader=reader,now_ms=NOW)
        self.assertEqual(requests,[("BTCUSDT",1,2**63-1)])
        self.assertEqual(out["schema"],"market_data.qualified-read-envelope.v1")
        self.assertEqual(out["api_version"],{"major":2,"minor":0})
        self.assertEqual(out["status"],"PARTIAL")
        self.assertEqual(out["record_integrity"],"VERIFIED")
        self.assertEqual(out["source_authenticity"],"NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(out["storage_immutability"],"NOT_ATTESTED")
        self.assertFalse(out["immutable"])
        self.assertFalse(out["trading_authorized"])
        self.assertFalse(out["paper_admitted"])
        self.assertFalse(out["execution_authority"])

    def test_invalid_cursor_and_limit_refused_before_database_call(self):
        def forbidden(*args):
            self.fail("invalid request attempted a SQL read")
        for limit,cursor in ((True,None),("01",None),("1001",None),(1,True),(1,"0"),(1,"9223372036854775808")):
            with self.subTest(limit=limit,cursor=cursor),self.assertRaises(ValueError):
                qualified_snapshot("BTCUSDT",limit,cursor,reader=forbidden,now_ms=NOW)

    def test_empty_source_is_unavailable_not_available(self):
        out=qualified_snapshot("BTCUSDT",1,reader=lambda *_:[],now_ms=NOW)
        self.assertEqual(out["status"],"UNAVAILABLE")
        self.assertEqual(out["rows"],[])
        self.assertFalse(out["trading_authorized"])
        self.assertFalse(out["paper_admitted"])

    def test_legacy_grid_producer_is_not_accepted_or_rehashed(self):
        data=canonical_fixture()
        data["producer"]="bybit-cluster-grid"
        data["dataset_fingerprint"]=digest({k:v for k,v in data.items() if k!="dataset_fingerprint"})
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_VERSION"):
            qualified_snapshot("BTCUSDT",1,reader=lambda *_:[data],now_ms=NOW)

    def test_managed_http_read_success_and_current_lease(self):
        handler=fake_handler()
        with patch("market_data.history_api.immutable_minutes",return_value=[canonical_fixture()]) as reader,patch("market_data_v2.read_api.time.time",return_value=NOW/1000):
            handler.do_GET()
        self.assertEqual(handler.out[0][0],200)
        self.assertEqual(handler.out[0][1]["status"],"PARTIAL")
        self.assertEqual(handler.server.startup_admission.calls,3)
        reader.assert_called_once_with("BTCUSDT",1,2**63-1)

    def test_unmanaged_wrong_bearer_and_revoked_lease_never_read(self):
        variants=[
            fake_handler(identity=False),
            fake_handler(token=None),
            fake_handler(token="c"*64),
            fake_handler(admission=Admission((False,))),
        ]
        for handler in variants:
            with patch("market_data.history_api.immutable_minutes",side_effect=AssertionError("unauthorized SQL read")):
                handler.do_GET()
            self.assertIn(handler.out[0][0],(401,503))

    def test_revocation_after_read_fails_closed_without_rows(self):
        handler=fake_handler(admission=Admission((True,True,False)))
        with patch("market_data.history_api.immutable_minutes",return_value=[canonical_fixture()]),patch("market_data_v2.read_api.time.time",return_value=NOW/1000):
            handler.do_GET()
        self.assertEqual(handler.out,[(503,{"error":"CURRENT_ADMISSION_REQUIRED"})])

    def test_broken_hash_yields_503_never_claims_client_400(self):
        handler=fake_handler()
        item=canonical_fixture()
        item["candle"]["high"]=0.1
        with patch("market_data.history_api.immutable_minutes",return_value=[item]),patch("market_data_v2.read_api.time.time",return_value=NOW/1000):
            handler.do_GET()
        self.assertEqual(handler.out,[(503,{"error":"SOURCE_RECORD_UNQUALIFIED"})])

    def test_invalid_query_fields_precede_read(self):
        for query in ("symbol=BTCUSDT&limit=01","symbol=BTCUSDT&limit=1&bad=x",
                      "symbol=BTCUSDT&symbol=ETHUSDT&limit=1","limit=1",
                      "symbol=BTCUSDT&limit=1&before_ms=0"):
            handler=fake_handler(path=ROUTE+"?"+query)
            with patch("market_data.history_api.immutable_minutes",side_effect=AssertionError("invalid SQL read")):
                handler.do_GET()
            self.assertEqual(handler.out[0][0],400)

    def test_no_real_network_transport_or_writer_in_route_source(self):
        import inspect
        import market_data_v2.read_api as route
        src=inspect.getsource(route)
        self.assertNotIn("websockets.connect",src)
        self.assertNotIn("asyncpg.create_pool",src)
        self.assertNotIn("INSERT INTO",src)
        self.assertNotIn("UPDATE provenance",src)

if __name__=="__main__":
    unittest.main()
