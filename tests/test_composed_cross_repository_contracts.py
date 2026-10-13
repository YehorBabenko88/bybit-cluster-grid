"""Offline synthetic contracts; set AUDIT_GRID_ROOT/AUDIT_STRATTESTER_ROOT/AUDIT_TERMINAN_ROOT.

Run: python -m pytest -q tests/test_composed_cross_repository_contracts.py
CI checks out immutable external revisions in .audit-contracts. Never uses a live source.
"""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".audit-contracts"
for env, directory in (("AUDIT_GRID_ROOT", "grid"),
                       ("AUDIT_STRATTESTER_ROOT", "strattester"),
                       ("AUDIT_TERMINAN_ROOT", "terminan")):
    sys.path.insert(0, os.environ.get(env, str(ROOT if directory == "grid" else WORK / directory)))

from grid.historical_science_import import canonical_payload, verify_bundle, import_historical_science
from strattester.marketdata.sqlite_store import Candle, SQLiteMarketStore
from strattester.research.scientific_bootstrap import export_scientific_bootstrap
from strattester.runtime.grid_handoff import file_sha256, write_handoff
from terminan import data


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    # Windows asyncio creates an internal loopback socket pair on loop startup.
    loop = asyncio.new_event_loop()
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden in synthetic contract tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    for name in ("TERMINAN_GRID_DSN", "TERMINAN_RESULTS_DB", "POSTGRES_DSN"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / "market.db"
    store = SQLiteMarketStore.open(path)
    records = [Candle("BTCUSDT", "1m", 1_700_000_000_000 + i * 60000,
                      100 + i, 102 + i, 99 + i, 101 + i, 10, 1000)
               for i in range(41)]
    assert store.upsert_candles(records).accepted == 41
    science_path = tmp_path / "science.json"
    exported = export_scientific_bootstrap(store, ["BTCUSDT"], science_path)
    store.close()
    monkeypatch.setenv("TERMINAN_STRATTESTER_DB", str(path))
    return path, science_path, exported


def test_real_strattester_science_is_accepted_by_grid(source):
    _, science, value = source
    assert verify_bundle(json.loads(science.read_text())) == (True, None)
    assert value["schema"] == 1
    assert value["symbols"][0]["symbol"] == "BTCUSDT"
    assert value["symbols"][0]["samples"] == 41
    assert value["research_scope"] == "HISTORICAL_BOOTSTRAP_ONLY"
    assert value["capabilities"]["true_l2_orderbook"] is False


def test_corrupted_scientific_payload_is_rejected(source):
    _, _, value = source
    value["symbols"][0]["samples"] += 1
    assert verify_bundle(value) == (False, "sha256 mismatch")


def test_even_signed_historical_bundle_cannot_claim_live_book(source):
    _, _, value = source
    value["capabilities"] = dict(value["capabilities"], true_l2_orderbook=True)
    value["sha256"] = hashlib.sha256(canonical_payload(value).encode()).hexdigest()
    assert verify_bundle(value) == (False, "fabricated historical live-only capability")


def test_handoff_hashes_the_exact_export_bytes(source, tmp_path):
    _, science, _ = source
    handoff = write_handoff(tmp_path / "handoff.json", science)
    assert handoff["science_bundle"]["sha256"] == file_sha256(science)
    science.write_text(science.read_text() + " ", encoding="utf-8")
    assert handoff["science_bundle"]["sha256"] != file_sha256(science)


def test_terminan_reads_real_strattester_schema_without_source_changes(source):
    path, _, _ = source
    before = path.read_bytes()
    rows = data.candles("BTCUSDT", "1m", 3)
    assert [row["t"] for row in rows] == [1700002280000, 1700002340000, 1700002400000]
    assert rows[-1]["c"] == 141
    assert data.instruments() == ["BTCUSDT"]
    assert path.read_bytes() == before


def test_terminan_sqlite_connection_enforces_readonly(source):
    path, _, _ = source
    before = path.read_bytes()
    conn = data.sqlite_ro("TERMINAN_STRATTESTER_DB")
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM candles")
    finally:
        conn.close()
    assert path.read_bytes() == before


def test_terminan_missing_grid_does_not_fabricate_market_data(monkeypatch):
    monkeypatch.delenv("TERMINAN_GRID_DSN", raising=False)
    assert data.grid_candles("BTCUSDT") == []
    assert data.footprint("BTCUSDT") == []


@pytest.mark.parametrize("adapter,width", [(data.grid_candles, 10), (data.footprint, 6)])
def test_terminan_postgres_adapters_request_readonly_parameterized_queries(monkeypatch, adapter, width):
    calls = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params): calls.append((sql, params))
        def fetchall(self): return [(1700000000000, *range(1, width))]

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()

    def connect(dsn, **kwargs):
        assert dsn == "synthetic-only"
        assert kwargs["connect_timeout"] == 3
        assert "default_transaction_read_only=on" in kwargs["options"]
        assert "statement_timeout=3000" in kwargs["options"]
        return Connection()

    monkeypatch.setenv("TERMINAN_GRID_DSN", "synthetic-only")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    assert adapter("BTCUSDT", 2000)[0]["t"] == 1700000000000
    assert len(calls) == 1
    sql, params = calls[0]
    assert sql.startswith("SELECT extract(epoch from ts)*1000")
    assert "BTCUSDT" not in sql
    assert params == ("BTCUSDT", 1000)


def test_real_export_reaches_historical_import_without_live_promotion(source, prohibit_network):
    _, _, value = source

    class SyntheticSink:
        def __init__(self):
            self.header = None
            self.symbols = []

        @asynccontextmanager
        async def acquire(self):
            yield self

        @asynccontextmanager
        async def transaction(self):
            yield

        async def fetchrow(self, sql, *args):
            assert "historical_scientific_bundles" in sql
            self.header = args
            return {"id": args[0], "status": "IMPORTED"}

        async def execute(self, sql, *args):
            assert "historical_scientific_symbol_state" in sql
            self.symbols.append(args)

    sink = SyntheticSink()
    result = prohibit_network.run_until_complete(import_historical_science(sink, value))
    assert result["live_evidence_promoted"] is False
    assert result["symbols"] == 1
    assert sink.header[2] == value["sha256"]
    assert sink.header[4] == "HISTORICAL_BOOTSTRAP_ONLY"
    assert sink.symbols[0][1] == "BTCUSDT"
    assert sink.symbols[0][3:6] == (41, 1700000000000, 1700002400000)
    assert json.loads(sink.symbols[0][7])["scalp_events"] == value["symbols"][0]["features"]["scalp_events"]
