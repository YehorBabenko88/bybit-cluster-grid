"""No-network tests for the proposed v1 qualified immutable read contract."""
import copy
import time
import unittest
from unittest.mock import patch
from market_data.provenance import minute_record, producer, digest
from market_data_v2.qualified_read_contract import (
    ProvenanceReadError, validate_minute, qualify_records,
)

NOW = 1800000120000
START = (NOW // 60000 - 1)*60000
SOURCE = producer("synthetic-grid-fixture","a"*40,"wss://stream.bybit.com/v5/public/linear")


def row(start=START, *, source=None):
    return dict(symbol="BTCUSDT",start_ms=start,
        source_event_start_ms=start+1,source_event_end_ms=start+59000,
        source_provenance=copy.deepcopy(SOURCE if source is None else source),
        open=1.0,high=2.0,low=1.0,close=2.0,buy_volume=1.0,
        sell_volume=0.0,delta=1.0,trade_count=1,poc_price=2.0,
        quality_status="GOOD",quality_reasons=[],
        levels=[{"price":2.0,"buy_volume":1.0,"sell_volume":0.0,
            "delta":1.0,"volume":1.0,"buy_count":1,"sell_count":0}])


def record(start=START, *, source=None):
    return minute_record(row(start,source=source),NOW,"synthetic-grid-fixture")


def resigned(r):
    r["dataset_fingerprint"]=digest({k:v for k,v in r.items() if k!="dataset_fingerprint"})
    return r


class QualifiedReadContractTests(unittest.TestCase):
    def test_valid_partial_record_is_never_available_or_trade_authorized(self):
        item=record()
        result=qualify_records([item],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["record_integrity"],"VERIFIED")
        self.assertEqual(result["source_authenticity"],"NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(result["exchange_completeness"],"NOT_ATTESTED")
        self.assertEqual(result["source_declared_quality"],["GOOD"])
        self.assertEqual(result["quality_attestation"],"NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(result["coverage"]["missing_minutes"],0)
        self.assertEqual(result["rows"],[item])
        self.assertIs(result["execution_authority"],False)
        self.assertIs(result["trading_authorized"],False)
        self.assertIs(result["immutable"],False)
        self.assertEqual(result["storage_immutability"],"NOT_ATTESTED")

    def test_corrupted_fingerprint_refused(self):
        item=record()
        item["candle"]["close"]=100
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_FINGERPRINT"):
            validate_minute(item,symbol="BTCUSDT",before_ms=NOW)

    def test_rehashed_false_completeness_refused(self):
        item=record()
        item["coverage"]["exchange_completeness_attested"]=True
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_COMPLETENESS_CLAIM"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)

    def test_rehashed_execution_authority_refused(self):
        item=record();item["execution_authority"]=True
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_EXECUTION_AUTHORITY"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)

    def test_wrong_symbol_and_source_revision_refused(self):
        item=record()
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_SYMBOL"):
            validate_minute(item,symbol="ETHUSDT",before_ms=NOW)
        item["source"]["source_revision"]="a"*39+"Z"
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_REVISION"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)

    def test_unknown_keys_and_nonfinite_refused(self):
        item=record();item["secret_extra"]="unsafe"
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_KEYS"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)
        item=record();item["candle"]["open"]=float("nan")
        with self.assertRaises(ProvenanceReadError):
            validate_minute(item,symbol="BTCUSDT",before_ms=NOW)

    def test_gap_and_duplicate_revision(self):
        first=record(START-120000)
        second=record(START)
        x=qualify_records([first,second],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(x["status"],"GAP")
        self.assertEqual(x["coverage"]["missing_minutes"],1)
        with self.assertRaisesRegex(ProvenanceReadError,"AMBIGUOUS_MINUTE_REVISIONS"):
            qualify_records([first,copy.deepcopy(first)],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)

    def test_epoch_boundary_is_gap_even_without_missing_minutes(self):
        first=record(START-60000)
        different=producer("synthetic-grid-fixture","a"*40,
            "wss://stream.bybit.com/v5/public/linear")
        second=record(START,source=different)
        x=qualify_records([first,second],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(x["status"],"GAP")
        self.assertEqual(x["coverage"]["missing_minutes"],0)

    def test_stale_and_unavailable(self):
        item=record(START-600000)
        x=qualify_records([item],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(x["status"],"STALE")
        unavailable=record()
        unavailable["status"]="UNAVAILABLE"
        unavailable["reason"]="SOURCE_PROVENANCE_UNAVAILABLE"
        unavailable["source_identity_verified"]=False
        x=qualify_records([resigned(unavailable)],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(x["status"],"UNAVAILABLE")
        self.assertEqual(x["rows"],[])

    def test_rehashed_invalid_numeric_candle_refused(self):
        item=record()
        item["candle"]["high"]=0.5
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_NUMERIC_INTEGRITY"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)

    def test_rehashed_invalid_footprint_refused(self):
        item=record()
        item["levels"][0]["buy_volume"]=999
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_NUMERIC_INTEGRITY"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)

    def test_future_provider_and_ingestion_clock_refused(self):
        item=record()
        with self.assertRaisesRegex(ProvenanceReadError,"QUERY_FUTURE_CLOCK"):
            qualify_records([item],symbol="BTCUSDT",before_ms=NOW+60000,now_ms=START)
        item=record()
        item["ingestion_ms"]=NOW+1
        with self.assertRaisesRegex(ProvenanceReadError,"QUERY_FUTURE_CLOCK"):
            qualify_records([resigned(item)],symbol="BTCUSDT",before_ms=NOW+60000,now_ms=NOW)

    def test_quality_label_does_not_grant_trading(self):
        item=record()
        item["quality_status"]="INVALID"
        x=qualify_records([resigned(item)],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        self.assertEqual(x["source_declared_quality"],["INVALID"])
        self.assertEqual(x["quality_attestation"],"NOT_INDEPENDENTLY_ATTESTED")
        self.assertIs(x["execution_authority"],False)
        self.assertIs(x["trading_authorized"],False)

    def test_empty_boolean_clocks_and_future_cursor_refused(self):
        with self.assertRaises(ProvenanceReadError):
            qualify_records([],symbol="BTCUSDT",before_ms=NOW,now_ms=NOW)
        item=record()
        item["start_ms"]=True
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_CLOCK"):
            validate_minute(resigned(item),symbol="BTCUSDT",before_ms=NOW)
        with self.assertRaisesRegex(ProvenanceReadError,"RECORD_TIME_BOUND"):
            validate_minute(record(),symbol="BTCUSDT",before_ms=START)

if __name__=="__main__":
    unittest.main()
