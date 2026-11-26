"""Native PG18 -> canonical SQL reader -> managed Grid v2 HTTP (owned LAB only).

This test deliberately does NOT patch market_data.history_api.immutable_minutes.
It requires the C-owned isolated LAB_POSTGRES_BIN, exact C source checkout,
and an ordinary non-root account. The test fails closed rather than producing
a fake passing / skipped PostgreSQL qualification when invoked without them.
Never point MARKET_DATA_DSN at any existing or user-owned database.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from email.message import Message
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from market_data.provenance import minute_record, producer, digest, canonical
from market_data_v2.read_api import Handler, ROUTE, qualified_snapshot

C_SHA="dcedaa870b5b8de566ff7bfa03182e3a43d19db5"
MATH_SHA="9e6acbd9e12a91189f57234828e31640983af553"
_SHA40=re.compile(r"[0-9a-f]{40}\Z")
_NOW_MS=1800000120000


class CurrentAdmission:
    def __init__(self, *states):
        self.states=list(states)
        self.calls=0

    def require_current(self):
        self.calls+=1
        return self.states.pop(0) if self.states else False


def require_owned_sources():
    grid_sha=os.environ.get("LAB_GRID_SHA")
    if not grid_sha or not re.fullmatch(r"[0-9a-f]{40}",grid_sha):
        raise RuntimeError("NATIVE_PG_GRID_SHA_MISSING")
    expected={"GRID_SOURCE_ROOT":grid_sha,"LAB_C_ROOT":C_SHA,
              "LAB_MATH_REPO":MATH_SHA}
    for variable,sha in expected.items():
        directory=os.environ.get(variable)
        if not directory:
            raise RuntimeError("NATIVE_PG_EXACT_SOURCE_MISSING:"+variable)
        root=Path(directory).resolve(strict=True)
        actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
                                       text=True).strip()
        if actual!=sha:
            raise RuntimeError("NATIVE_PG_SOURCE_SHA_MISMATCH:"+variable)
    if sys.platform.startswith("linux") and os.geteuid()==0:
        raise RuntimeError("NATIVE_PG_ROOT_USER_REJECTED")
    pg_bin=os.environ.get("LAB_POSTGRES_BIN")
    if not pg_bin or not Path(pg_bin).is_absolute():
        raise RuntimeError("NATIVE_PG_18_BIN_MISSING")


def source_minute():
    start=(_NOW_MS//60000-1)*60000
    source=producer("isolated-grid-pg18","a"*40,
                    "wss://stream.bybit.com/v5/public/linear")
    record=minute_record({
        "symbol":"BTCUSDT","start_ms":start,
        "source_event_start_ms":start+1,"source_event_end_ms":start+59000,
        "source_provenance":source,
        "open":1.0,"high":2.0,"low":1.0,"close":2.0,
        "buy_volume":1.0,"sell_volume":0.0,"delta":1.0,
        "trade_count":1,"poc_price":2.0,
        "quality_status":"GOOD","quality_reasons":[],
        "levels":[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
                   "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}],
    },_NOW_MS,"isolated-grid-pg18")
    if record["status"]!="PARTIAL":
        raise AssertionError("NATIVE_PG_CANONICAL_PRODUCER_NOT_PARTIAL")
    return record


def fake_handler(pg, admission=None):
    obj=object.__new__(Handler)
    obj.server=SimpleNamespace(
        startup_admission=admission or CurrentAdmission(True,True,True),
        module_identity={"instance_token":"b"*64})
    obj.headers=Message()
    obj.headers.add_header("Authorization","Bearer "+"b"*64)
    obj.path=ROUTE+"?symbol=BTCUSDT&limit=1"
    obj.out=[]
    obj._json=lambda status,body:obj.out.append((status,body))
    return obj


class NativePG18GridRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_owned_sources()
        croot=Path(os.environ["LAB_C_ROOT"]).resolve(strict=True)
        sys.path.insert(0,str(croot))
        from unified_system.lab_postgres import LabPostgres
        from tests.test_lab_postgres import canonical_schema
        cls.LabPostgres=LabPostgres
        cls.schema=canonical_schema

    @classmethod
    def tearDownClass(cls):
        croot=os.environ.get("LAB_C_ROOT")
        if croot and str(Path(croot).resolve()) in sys.path:
            sys.path.remove(str(Path(croot).resolve()))

    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix="market-data-v2-owned-pg-"))
        if os.name!="nt":
            self.root.chmod(0o700)
        self.pg=None

    def tearDown(self):
        try:
            if self.pg is not None:
                self.pg.stop()
        finally:
            if self.pg is None or not self.pg.started:
                shutil.rmtree(self.root)

    def start_pg(self):
        # Retain owner identity even if init/start fails: cleanup must never
        # delete a live or foreign postmaster tree by accident.
        self.pg=self.LabPostgres(os.environ["LAB_POSTGRES_BIN"],self.root,min_major=18)
        self.pg.initialize().start().provision(self.schema())
        if self.pg.major!=18 or self.pg.port==5432:
            raise AssertionError("NATIVE_PG_UNSAFE_VERSION_OR_PORT")
        witness=self.pg.provenance_storage_witness()
        if witness["witness_schema"]!="lab-postgres-custody.v1":
            raise AssertionError("NATIVE_PG_CUSTODY_MISSING")
        return self.pg

    def insert(self,record):
        blob=canonical(record).decode("utf-8").replace("'","''")
        fingerprint=record["dataset_fingerprint"]
        content_id=digest(record)
        self.pg.sql(
            "INSERT INTO provenance_minutes(fingerprint,content_id,symbol,start_ms,record)"
            f" VALUES ('{fingerprint}','{content_id}','BTCUSDT',{record['start_ms']},'{blob}'::jsonb)",
            role="lab_writer")

    def test_real_psycopg_read_and_managed_http_partial_only(self):
        pg=self.start_pg()
        record=source_minute()
        self.insert(record)
        # Real role-scoped psycopg, no reader mock or in-memory database seam.
        with patch.dict(os.environ,{"MARKET_DATA_DSN":pg.dsn("lab_reader")}):
            out=qualified_snapshot("BTCUSDT",1,now_ms=_NOW_MS)
            self.assertEqual(out["status"],"PARTIAL")
            self.assertEqual(out["rows"][0]["dataset_fingerprint"],record["dataset_fingerprint"])
            self.assertEqual(out["source_authenticity"],"NOT_INDEPENDENTLY_ATTESTED")
            self.assertEqual(out["storage_immutability"],"NOT_ATTESTED")
            self.assertFalse(out["paper_admitted"])
            handler=fake_handler(pg)
            with patch("market_data_v2.read_api.time.time",return_value=_NOW_MS/1000):
                handler.do_GET()
            self.assertEqual(handler.out[0][0],200)
            self.assertEqual(handler.out[0][1]["status"],"PARTIAL")
            self.assertFalse(handler.out[0][1]["trading_authorized"])
            self.assertFalse(handler.out[0][1]["paper_admitted"])
            self.assertEqual(handler.server.startup_admission.calls,3)
            # The exact authenticated read role cannot INSERT.
            with self.assertRaises(Exception):
                pg.sql("INSERT INTO provenance_minutes(fingerprint,content_id,symbol,start_ms,record)"
                       " VALUES ('"+("f"*64)+"','"+("e"*64)+"','BTCUSDT',0,'{}'::jsonb)",
                       role="lab_reader")

    def test_real_pg18_over_private_http_socket(self):
        pg=self.start_pg()
        record=source_minute()
        self.insert(record)
        admission=CurrentAdmission(*([True]*10))
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        server.daemon_threads=True
        server.startup_admission=admission
        server.module_identity={"instance_token":"b"*64}
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            with patch.dict(os.environ,{"MARKET_DATA_DSN":pg.dsn("lab_reader")}):
                with patch("market_data_v2.read_api.time.time",return_value=_NOW_MS/1000):
                    connection=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
                    try:
                        connection.request("GET",ROUTE+"?symbol=BTCUSDT&limit=1",
                                           headers={"Authorization":"Bearer "+"b"*64})
                        result=connection.getresponse()
                        code=result.status
                        body=json.loads(result.read())
                    finally:
                        connection.close()
            self.assertEqual(code,200)
            self.assertEqual(body["status"],"PARTIAL")
            self.assertEqual(body["rows"][0]["dataset_fingerprint"],
                             record["dataset_fingerprint"])
            self.assertEqual(body["source_authenticity"],"NOT_INDEPENDENTLY_ATTESTED")
            self.assertEqual(body["storage_immutability"],"NOT_ATTESTED")
            self.assertFalse(body["paper_admitted"])
            self.assertFalse(body["execution_authority"])
            self.assertEqual(admission.calls,3)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive(),"NATIVE_HTTP_LISTENER_NOT_CLOSED")

    def test_real_pg_tampered_record_503_and_legacy_producer_refusal(self):
        pg=self.start_pg()
        record=source_minute()
        tampered=json.loads(canonical(record))
        tampered["producer"]="bybit-cluster-grid"
        tampered["dataset_fingerprint"]=digest({k:v for k,v in tampered.items()
                                                 if k!="dataset_fingerprint"})
        self.insert(tampered)
        with patch.dict(os.environ,{"MARKET_DATA_DSN":pg.dsn("lab_reader")}):
            handler=fake_handler(pg)
            with patch("market_data_v2.read_api.time.time",return_value=_NOW_MS/1000):
                handler.do_GET()
            self.assertEqual(handler.out,[(503,{"error":"SOURCE_RECORD_UNQUALIFIED"})])

    def test_real_pg_auth_and_post_read_lease_refusal(self):
        pg=self.start_pg()
        self.insert(source_minute())
        with patch.dict(os.environ,{"MARKET_DATA_DSN":pg.dsn("lab_reader")}):
            handler=fake_handler(pg,CurrentAdmission(True,True,False))
            with patch("market_data_v2.read_api.time.time",return_value=_NOW_MS/1000):
                handler.do_GET()
            self.assertEqual(handler.out,[(503,{"error":"CURRENT_ADMISSION_REQUIRED"})])
            self.assertEqual(handler.server.startup_admission.calls,3)
            handler=fake_handler(pg)
            handler.headers=Message()
            with patch("market_data_v2.read_api.time.time",return_value=_NOW_MS/1000):
                handler.do_GET()
            self.assertEqual(handler.out[0][0],401)

    def test_real_pg_empty_read_is_unavailable_and_writer_update_denied(self):
        pg=self.start_pg()
        with patch.dict(os.environ,{"MARKET_DATA_DSN":pg.dsn("lab_reader")}):
            handler=fake_handler(pg)
            handler.do_GET()
            self.assertEqual(handler.out[0][0],200)
            self.assertEqual(handler.out[0][1]["status"],"UNAVAILABLE")
            self.assertEqual(handler.out[0][1]["rows"],[])
        self.insert(source_minute())
        with self.assertRaises(Exception):
            pg.sql("UPDATE provenance_minutes SET symbol='ETHUSDT'",
                   role="lab_writer")


if __name__=="__main__":
    unittest.main()
