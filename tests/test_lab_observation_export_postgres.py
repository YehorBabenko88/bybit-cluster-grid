"""Actual public-observation SQL contract; only the reviewed hosted PG18 fixture.

No ambient POSTGRES_DSN is consulted. All writes belong to one generated private
schema. These tests do not establish exchange provenance or paper-trading trust.
"""
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import uuid

import pytest
from grid.lab_observation_export import read_postgres, ExportBlocked, SYMBOLS

FIXED_DSN = 'postgresql://grid:grid@127.0.0.1:5432/grid'


def _disposable_dsn(environ):
    expected = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid',
        GITHUB_JOB='linux-postgres18', HISTORY_DISPOSABLE_DSN=FIXED_DSN,
        MISSION3_TEST_DATABASE_URL=FIXED_DSN)
    if any(environ.get(k) != v for k, v in expected.items()):
        raise ValueError('DISPOSABLE_PG_JOB_REQUIRED')
    return FIXED_DSN


def _schema(value):
    if type(value) is not str or re.fullmatch(r'market_export_[0-9a-f]{32}', value) is None:
        raise ValueError('PRIVATE_SCHEMA_REQUIRED')
    return value


def _market_ddl():
    # Use production DDL without importing configuration or running migrations
    # against public. A schema change must update the real positive SQL test.
    tree = ast.parse((Path(__file__).parents[1] / 'grid' / 'db.py').read_text(encoding='utf-8'))
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = re.search(r'CREATE TABLE IF NOT EXISTS market_events\(.*?\n\s*\);', node.value, re.S)
            if match:
                matches.append(match.group())
    assert len(matches) == 1
    return matches[0]


def test_fixture_admission_rejects_ambient_and_foreign_targets_before_connect():
    good = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid', GITHUB_JOB='linux-postgres18',
        HISTORY_DISPOSABLE_DSN=FIXED_DSN, MISSION3_TEST_DATABASE_URL=FIXED_DSN)
    assert _disposable_dsn(good) == FIXED_DSN
    for key in good:
        bad = dict(good); bad[key] = 'unapproved'
        with pytest.raises(ValueError, match='DISPOSABLE_PG_JOB_REQUIRED'):
            _disposable_dsn(bad)
    with pytest.raises(ValueError):
        _disposable_dsn({'POSTGRES_DSN': FIXED_DSN})
    for bad in ('public', 'market_export_../public', 'market_export_' + 'a'*31):
        with pytest.raises(ValueError): _schema(bad)
    assert 'UNIQUE(symbol,event_ts,event_type,payload)' in _market_ddl()


def _public(conn):
    return conn.execute("SELECT c.oid::bigint,c.relname,c.relkind FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid").fetchall()


@pytest.fixture
def database():
    if not os.environ.get('HISTORY_DISPOSABLE_DSN'):
        pytest.skip('actual disposable PostgreSQL unavailable; NOT_RUN')
    dsn = _disposable_dsn(os.environ)  # Guard MUST precede import/connect.
    import psycopg
    name = _schema('market_export_' + uuid.uuid4().hex)
    admin = psycopg.connect(dsn, autocommit=True, options='-c search_path=pg_catalog')
    created = False
    connections = []
    before = _public(admin)
    try:
        assert 180000 <= int(admin.execute('SHOW server_version_num').fetchone()[0]) < 190000
        admin.execute(f'CREATE SCHEMA "{name}"'); created = True
        def connect():
            # Applied on EVERY connection, not only on one initializer checkout.
            conn = psycopg.connect(dsn, autocommit=True, options=f'-c search_path={name}')
            connections.append(conn)
            assert conn.execute('SELECT current_schema()').fetchone()[0] == name
            assert conn.execute('SELECT current_schemas(false)').fetchone()[0] == [name]
            return conn
        writer = connect()
        writer.execute(_market_ddl())
        yield writer, connect
    finally:
        try:
            for conn in connections: conn.close()
            if created: admin.execute(f'DROP SCHEMA "{name}" CASCADE')
            assert _public(admin) == before, 'public object inventory changed'
        finally:
            admin.close()


def _insert(conn, symbol='BTCUSDT', ms=1700000000000, *, micros=0, kind='derivatives_ticker', payload=None):
    from psycopg.types.json import Jsonb
    from datetime import timedelta
    stamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms, microseconds=micros)
    return conn.execute('INSERT INTO market_events(symbol,event_ts,event_type,payload) VALUES(%s,%s,%s,%s) RETURNING id',
        (symbol, stamp, kind, Jsonb(payload if payload is not None else {'last_price': '123.45'}))).fetchone()[0]


def _request(symbol='BTCUSDT'):
    return dict(symbol=symbol, start_ms=1700000000000, end_ms=1700000001000,
                as_of_ms=1700000000500, max_age_ms=100)


def _snapshot(conn):
    return conn.execute('SELECT id,symbol,event_ts,event_type,source,payload,ingest_ts FROM market_events ORDER BY id').fetchall()


def test_real_ten_symbols_half_open_microseconds_freshness_and_no_source_mutation(database):
    writer, connect = database
    for symbol in sorted(SYMBOLS):
        _insert(writer, symbol, ms=1699999999999)
        _insert(writer, symbol, micros=123, payload={'last_price':'123.45', 'bid1_price':'122', 'secret_unrecognized':'omitted', '_quality':{'symbol':symbol,'feeds':{'ticker':{'status':'available','reason':'private text'}}}})
        _insert(writer, symbol, ms=1700000000500, kind='orderbook_snapshot', payload={'sequence':17,'update_id':19,'cts':1700000000500,'best_bid':'122','best_ask':'124'})
        _insert(writer, symbol, ms=1700000000900)
        _insert(writer, symbol, ms=1700000001000)
        _insert(writer, symbol, ms=1700000000100, kind='trade', payload={'price':'1'})
    before = _snapshot(writer)
    reader = connect()
    for symbol in sorted(SYMBOLS):
        result = read_postgres(reader, _request(symbol))
        assert result['row_count'] == 3
        rows = result['rows']
        assert [r['observation_status'] for r in rows] == ['stale','observed','future']
        assert rows[0]['event_ts'].endswith('000123+00:00')
        assert rows[0]['event_age_ms'] == 499.877
        assert rows[1]['payload']['sequence'] == 17 and rows[1]['payload']['update_id'] == 19
        assert all(r['field_freshness'] == 'unknown' and r['source'] == 'bybit' for r in rows)
        assert 'secret_unrecognized' not in rows[0]['payload']
        assert rows[0]['payload']['_quality']['feeds']['ticker'] == {'status':'available'}
        assert result['source_completeness'] == 'NOT_EVALUATED'
        assert result['execution_authority'] is False and result['trading_authorized'] is False
        assert reader.info.transaction_status == 0
    assert _snapshot(writer) == before


class _InspectConnection:
    def __init__(self, conn, concurrent_insert):
        self.conn = conn; self.info = conn.info; self.concurrent_insert = concurrent_insert
        self.observed = False
    def transaction(self): return self.conn.transaction()
    @contextmanager
    def cursor(self):
        with self.conn.cursor() as cur:
            parent = self
            class Cursor:
                def execute(self, sql, params=None):
                    if sql.startswith('SELECT CASE'):
                        assert parent.conn.execute('SHOW transaction_isolation').fetchone()[0] == 'repeatable read'
                        assert parent.conn.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
                        # Establish the snapshot before a second committed writer.
                        assert parent.conn.execute('SELECT count(*) FROM market_events').fetchone()[0] == 1
                        import psycopg
                        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                            with parent.conn.transaction():
                                parent.conn.execute("UPDATE market_events SET source='forbidden'")
                        parent.concurrent_insert()
                        parent.observed = True
                    return cur.execute(sql, params)
                def fetchall(self): return cur.fetchall()
            yield Cursor()


def test_real_readonly_repeatable_read_snapshot_and_connection_ownership(database):
    writer, connect = database
    _insert(writer)
    reader = connect()
    inspected = _InspectConnection(reader, lambda: _insert(writer, ms=1700000000200))
    result = read_postgres(inspected, _request())
    assert inspected.observed and result['row_count'] == 1
    assert writer.execute('SELECT count(*) FROM market_events').fetchone()[0] == 2
    assert reader.closed is False and reader.info.transaction_status == 0
    with reader.transaction():
        with pytest.raises(ExportBlocked, match='BLOCKED_ACTIVE_TRANSACTION'):
            read_postgres(reader, _request())
        assert reader.execute('SELECT 1').fetchone() == (1,)


def test_real_row_and_raw_json_budget_fail_closed_without_mutation(database):
    writer, connect = database
    from psycopg.types.json import Jsonb
    for index in range(1001):
        _insert(writer, micros=index)
    before = _snapshot(writer)
    reader = connect()
    with pytest.raises(ExportBlocked, match='BLOCKED_ROW_LIMIT'):
        read_postgres(reader, _request())
    assert _snapshot(writer) == before and reader.info.transaction_status == 0
    # Caller owns this private fixture, not exporter. Unknown fields still count
    # toward raw bytes even though they would be omitted from safe projection.
    writer.execute('DELETE FROM market_events')
    _insert(writer, payload={'last_price':'1','unknown':'x' * 1048577})
    before = _snapshot(writer)
    with pytest.raises(ExportBlocked, match='BLOCKED_BYTE_LIMIT'):
        read_postgres(reader, _request())
    assert _snapshot(writer) == before and reader.info.transaction_status == 0


def test_real_aggregate_raw_budget_and_invalid_source_roll_back_cleanly(database):
    writer, connect = database
    for index in range(9):
        _insert(writer, micros=index, payload={'last_price':'1','unknown':'x' * 960000})
    before = _snapshot(writer)
    reader = connect()
    with pytest.raises(ExportBlocked, match='BLOCKED_BYTE_LIMIT'):
        read_postgres(reader, _request())
    assert _snapshot(writer) == before and reader.info.transaction_status == 0
    writer.execute('DELETE FROM market_events')
    _insert(writer)
    writer.execute("UPDATE market_events SET source='untrusted-fixture'")
    before = _snapshot(writer)
    with pytest.raises(ExportBlocked, match='BLOCKED_ROW'):
        read_postgres(reader, _request())
    assert _snapshot(writer) == before and reader.info.transaction_status == 0
    # A rejected transaction must not poison a later positive export.
    writer.execute("UPDATE market_events SET source='bybit'")
    assert read_postgres(reader, _request())['row_count'] == 1
