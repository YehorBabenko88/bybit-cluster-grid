import pytest
from grid import terminan_gateway as gateway

V4_TWO_HOUR_FIXTURE_PIN = 'c74e4eadb337a9463bf42b0c33e3dc051839e4374301b0b8e19ee71f28a8a032'


def test_capabilities_exposes_no_qualified_market_data(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: pytest.fail('capabilities must be offline'))
    result = gateway.snapshot('/internal/v1/capabilities')
    assert result['api_version'] == {'major': 1, 'minor': 0}
    assert result['read_only'] is True
    assert result['capabilities']['live_l2'] is False
    assert result['capabilities']['candles'] == 'UNAVAILABLE'
    assert result['source']['market_type'] is None
    assert result['source']['epoch'] is None


@pytest.mark.parametrize('route', ['/internal/v1/candles', '/internal/v1/footprint'])
def test_unknown_provenance_never_queries_or_returns_rows(monkeypatch, route):
    monkeypatch.setattr(gateway, 'query', lambda *a: pytest.fail('unqualified market data query'))
    result = gateway.snapshot(route, 'BTCUSDT', 1000)
    assert result['status'] == 'UNAVAILABLE'
    assert result['rows'] == []
    assert result['reason'] == 'SOURCE_PROVENANCE_UNAVAILABLE'


@pytest.mark.parametrize('limit', [0, 1001, True, 1.5, '1.5', '-1'])
def test_versioned_bounds_reject_instead_of_coercing(limit):
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/candles', 'BTCUSDT', limit)


def test_health_db_reachability_is_not_market_readiness(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: [(180001, 'on')])
    result = gateway.snapshot('/internal/v1/health')
    assert result['database'] == 'READ_ONLY'
    assert result['status'] == 'UNAVAILABLE'


def test_health_fails_closed_if_database_not_readonly(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: [(180001, 'off')])
    assert gateway.snapshot('/internal/v1/health')['database'] == 'UNAVAILABLE'

@pytest.mark.parametrize('rows', [[(160000, 'on')], [], [(180001, 'off')]])
def test_health_requires_pg18_readonly(rows, monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: rows)
    assert gateway.snapshot('/internal/v1/health')['database'] == 'UNAVAILABLE'


def test_health_redacts_source_exception(monkeypatch):
    def failing(*args):
        raise RuntimeError('password=secret')
    monkeypatch.setattr(gateway, 'query', failing)
    result = gateway.snapshot('/internal/v1/health')
    assert 'secret' not in str(result)
    assert result['database'] == 'UNAVAILABLE'


def test_disposable_pg18_health(monkeypatch):
    import os
    dsn = os.environ.get('TERMINAN_DISPOSABLE_PG18_DSN')
    if not dsn:
        pytest.skip('explicit disposable PostgreSQL 18 DSN required')
    monkeypatch.setenv('TERMINAN_GRID_DSN', dsn)
    result = gateway.snapshot('/internal/v1/health')
    assert result['database'] == 'READ_ONLY'
    assert result['status'] == 'UNAVAILABLE'

def test_legacy_nodes_route_no_longer_exposes_cluster_inventory(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Grid must not query cross-host node inventory')
    monkeypatch.setattr(gateway, 'query', forbidden)
    result = gateway.snapshot('/v1/nodes', 'BTCUSDT', 1)
    assert result == {'version': 1, 'status': 'UNAVAILABLE',
                      'reason': 'UNIFIED_SYSTEM_NODE_OWNER', 'nodes': []}


def test_grid_backfill_state_is_informational_not_coverage(monkeypatch):
    from datetime import datetime, timezone
    recorded = []
    def read(sql, args=()):
        recorded.append((sql, args))
        return [('done', 3, 0, datetime(2026, 1, 1, tzinfo=timezone.utc),
                 datetime(2026, 1, 2, tzinfo=timezone.utc))]
    monkeypatch.setattr(gateway, 'query', read)
    result = gateway.snapshot('/internal/v1/backfill-state', 'BTCUSDT')
    assert len(recorded) == 1
    assert recorded[0][1] == ('BTCUSDT',)
    assert 'market_backfill_state' in recorded[0][0]
    assert 'SELECT' in recorded[0][0]
    assert result['state'] == 'done'
    assert result['status'] == 'INFORMATIONAL'
    assert result['history_coverage'] == 'NOT_ATTESTED'
    assert result['source_provenance'] == 'NOT_ATTESTED'
    assert result['oldest_loaded_utc'] == '2026-01-01T00:00:00Z'
    assert result['next_end_ms'] == 0
    assert result['read_only'] is True
    assert result['execution_authority'] is False
    assert result['trading_authorized'] is False
    assert 'last_error' not in result


def test_grid_backfill_no_record_is_not_ready(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: [])
    result = gateway.snapshot('/internal/v1/backfill-state', 'BTCUSDT')
    assert result['status'] == 'UNAVAILABLE'
    assert result['state'] == 'UNKNOWN'
    assert result['history_coverage'] == 'NOT_ATTESTED'


@pytest.mark.parametrize('bad', [
    [('READY', 1, 0, None, None)],
    [('done', True, 0, None, None)],
    [('done', -1, 0, None, None)],
    [('done', 1, '0', None, None)],
    [('done', 1, 0, 'not-a-timestamp', None)],
    [('done', 1, 0, None, None), ('done', 1, 0, None, None)],
])
def test_grid_backfill_refuses_malformed_or_ambiguous_rows(monkeypatch, bad):
    monkeypatch.setattr(gateway, 'query', lambda *a: bad)
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/backfill-state', 'BTCUSDT')


@pytest.mark.parametrize('symbol', ['../BTC', 'btcUSDT', '', None, True])
def test_grid_backfill_rejects_bad_symbol_before_db(monkeypatch, symbol):
    monkeypatch.setattr(gateway, 'query', lambda *a: pytest.fail('DB must not be queried'))
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/backfill-state', symbol)


def test_grid_backfill_rejects_unsupported_cursor_before_db(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: pytest.fail('DB must not be queried'))
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/backfill-state', 'BTCUSDT', before_ms='42')


@pytest.mark.parametrize('path', [
    '/internal/v1/backfill-state',
    '/internal/v1/backfill-state?limit=1',
    '/internal/v1/backfill-state?symbol=BTCUSDT&before_ms=1',
    '/internal/v1/backfill-state?symbol=BTCUSDT&symbol=ETHUSDT',
])
def test_backfill_http_requires_single_explicit_instrument(monkeypatch, path):
    import io, json
    monkeypatch.setattr(gateway, 'snapshot', lambda *a: pytest.fail('must reject before dispatch'))
    handler = object.__new__(gateway.Handler)
    handler.path = path
    handler.wfile = io.BytesIO()
    statuses = []
    handler.send_response = lambda status: statuses.append(status)
    handler.send_header = lambda *a: None
    handler.end_headers = lambda: None
    handler.do_GET()
    assert statuses == [400]
    assert json.loads(handler.wfile.getvalue())['error'] == 'INVALID_QUERY_OR_ROUTE'


def test_grid_instrument_registry_read_only_not_live(monkeypatch):
    from datetime import datetime, timezone
    from decimal import Decimal
    calls = []
    def reader(sql, args):
        calls.append((sql, args))
        return [('Trading', 'LinearPerpetual', Decimal('0.00010000'),
                 datetime(2026, 11, 19, tzinfo=timezone.utc))]
    monkeypatch.setattr(gateway, 'query', reader)
    result = gateway.snapshot('/internal/v1/instrument-state', 'BTCUSDT')
    assert calls[0][1] == ('BTCUSDT',)
    assert 'FROM instruments' in calls[0][0]
    assert result['recorded_status'] == 'Trading'
    assert result['status'] == 'INFORMATIONAL'
    assert result['market_type'] == 'linear'
    assert result['tick_size'] == '0.00010000'
    assert result['last_seen_utc'] == '2026-11-19T00:00:00Z'
    assert result['exchange_connection'] == 'NOT_ATTESTED'
    assert result['history_coverage'] == 'NOT_ATTESTED'
    assert result['trading_authorized'] is False


def test_grid_instrument_not_found_never_implies_trading(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: [])
    result = gateway.snapshot('/internal/v1/instrument-state', 'BTCUSDT')
    assert result['status'] == 'UNAVAILABLE'
    assert result['exchange_connection'] == 'NOT_ATTESTED'


@pytest.mark.parametrize('rows', [
    [('Active', 'LinearPerpetual', None, None)],
    [('Trading', 10, None, None)],
    [('Trading', 'LinearPerpetual', 0.1, None)],
    [('Trading', 'LinearPerpetual', None, 'not datetime')],
    [('Trading', 'LinearPerpetual', None, None)] * 2,
])
def test_grid_instrument_rejects_ambiguous_or_unqualified_rows(monkeypatch, rows):
    monkeypatch.setattr(gateway, 'query', lambda *a: rows)
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/instrument-state', 'BTCUSDT')


@pytest.mark.parametrize('path', [
    '/internal/v1/instrument-state',
    '/internal/v1/instrument-state?symbol=BTCUSDT&limit=1',
    '/internal/v1/instrument-state?symbol=BTCUSDT&before_ms=42',
])
def test_instrument_http_requires_exact_symbol_only(monkeypatch, path):
    import io, json
    monkeypatch.setattr(gateway, 'snapshot', lambda *a: pytest.fail('must reject before dispatch'))
    handler = object.__new__(gateway.Handler)
    handler.path = path
    handler.wfile = io.BytesIO()
    statuses = []
    handler.send_response = lambda status: statuses.append(status)
    handler.send_header = lambda *a: None
    handler.end_headers = lambda: None
    handler.do_GET()
    assert statuses == [400]
    assert json.loads(handler.wfile.getvalue())['error'] == 'INVALID_QUERY_OR_ROUTE'

def test_meta_absorption_capabilities_do_not_claim_live_or_cutover(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *a: pytest.fail('capability discovery must not query market data'))
    response = gateway.snapshot('/internal/v1/capabilities')
    caps = response['capabilities']
    for dataset in ('public_trades', 'orderbook_snapshots', 'open_interest', 'funding_rate'):
        assert caps[dataset] == 'UNAVAILABLE'
    assert caps['market_data_coverage'] == 'NOT_ATTESTED'
    assert caps['replay_cursor'] == 'NOT_ATTESTED'
    assert response['meta_absorption'] == {
        'schema': 'grid.meta.dataset-capabilities.v1',
        'exchange_owner': 'Grid',
        'database_writer_owner': 'Grid',
        'history_provenance': 'NOT_ATTESTED',
        'consumer_cutover': False,
        'execution_authority': False,
        'trading_authorized': False,
    }

@pytest.mark.parametrize('route', [
    '/internal/v1/trades', '/internal/v1/orderbook', '/internal/v1/open-interest',
    '/internal/v1/funding', '/internal/v1/mark-price', '/internal/v1/index-price',
    '/internal/v1/premium-index',
])
def test_unqualified_raw_dataset_routes_refuse_source_without_db(monkeypatch, route):
    monkeypatch.setattr(gateway, 'query', lambda *args: pytest.fail('unqualified dataset must not query DB'))
    monkeypatch.setattr(gateway, 'immutable_minutes', lambda *args: pytest.fail('unqualified dataset must not read aggregate'))
    response = gateway.snapshot(route, 'BTCUSDT', 100)
    assert response['api_version'] == {'major': 1, 'minor': 0}
    assert response['status'] == 'UNAVAILABLE'
    assert response['reason'] == 'SOURCE_PROVENANCE_UNAVAILABLE'
    assert response['source_provenance'] == 'NOT_ATTESTED'
    assert response['coverage'] == 'NOT_ATTESTED'
    assert response['sequence'] == 'NOT_ATTESTED'
    assert response['rows'] == []
    assert response['execution_authority'] is False
    assert response['trading_authorized'] is False

@pytest.mark.parametrize('symbol,limit,cursor', [
    ('../BTC', 1, None), ('BTCUSDT', 0, None),
    ('BTCUSDT', 1001, None), ('BTCUSDT', True, None),
    ('BTCUSDT', 1, '-1'), ('BTCUSDT', 1, '99999999999999999'),
])
def test_unqualified_raw_dataset_routes_validate_before_io(monkeypatch, symbol, limit, cursor):
    monkeypatch.setattr(gateway, 'query', lambda *args: pytest.fail('invalid request must not query DB'))
    with pytest.raises(ValueError):
        gateway.snapshot('/internal/v1/trades', symbol, limit, cursor)


def test_pinned_history_reuses_immutable_selection_without_new_store(monkeypatch):
    import sys
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture, Connection
    rows, selection, catalog, expected = snapshot_fixture()
    class ReadOnly(Connection):
        def __enter__(self): return self
        def __exit__(self, *args): return False
    conn=ReadOnly(rows)
    observations=[]
    def connect(dsn, **kwargs):
        observations.append((dsn,kwargs))
        return conn
    monkeypatch.setenv('TERMINAN_GRID_DSN','test-only-readonly')
    monkeypatch.setattr(gateway,'_snapshot_catalog',lambda:catalog)
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(connect=connect))
    result=gateway.pinned_history(selection)
    assert result['schema']=='grid.history.snapshot.response.v1'
    assert result['read_only'] is True
    assert result['source_authentication']=='EXTERNAL_NOT_INDEPENDENTLY_VERIFIED'
    assert result['execution_authority'] is False
    assert result['trading_authorized'] is False
    assert result['snapshot']==expected
    assert len(observations)==1
    assert observations[0][1]['options'].find('default_transaction_read_only=on')>=0
    assert 'REPEATABLE READ READ ONLY' in conn.calls[0][0]
    assert any('fingerprint = ANY(%s)' in sql for sql,_ in conn.calls)


def test_pinned_history_requires_independent_catalog_before_db(monkeypatch):
    import sys
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture
    rows, selection, catalog, expected = snapshot_fixture()
    monkeypatch.delenv('GRID_PINNED_HISTORY_CATALOG',raising=False)
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(
        connect=lambda *a,**k:pytest.fail('no catalog means no database connection')))
    with pytest.raises(RuntimeError):
        gateway.pinned_history(selection)


@pytest.mark.parametrize('timeframe,minutes', [('5m', 5), ('15m', 15), ('1h', 60)])
def test_pinned_history_rollup_binds_exact_minutes(monkeypatch, timeframe, minutes):
    import sys
    from types import SimpleNamespace
    from grid.provenance import digest
    from test_history_snapshot import Connection, snapshot_fixture

    rows, selection, catalog, parent = snapshot_fixture(120, 'HISTORICAL')
    conn = Connection(rows)
    monkeypatch.setenv('TERMINAN_GRID_DSN', 'test-only-readonly')
    monkeypatch.setattr(gateway, '_snapshot_catalog', lambda: catalog)
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda *a, **k: conn))
    request = dict(selection, schema='grid.history.selection.v2', timeframe=timeframe)
    response = gateway.pinned_history(request)
    assert response['schema'] == 'grid.history.snapshot.response.v2'
    assert response['source_authentication'] == 'EXTERNAL_NOT_INDEPENDENTLY_VERIFIED'
    assert response['read_only'] and not response['execution_authority'] and not response['trading_authorized']
    snapshot = response['snapshot']
    assert snapshot['timeframe'] == timeframe
    assert snapshot['parent_dataset_id'] == parent['dataset_id']
    assert snapshot['parent_dataset_fingerprint'] == parent['dataset_fingerprint']
    assert snapshot['dataset_fingerprint'] == digest({k: v for k, v in snapshot.items() if k != 'dataset_fingerprint'})
    assert len(snapshot['rows']) == 120 // minutes
    assert snapshot['rows'][0] == {
        'event_start_ms': 0, 'event_end_ms': minutes * 60000,
        'open': 100, 'high': 102 + (minutes - 1) * .1,
        'low': 99, 'close': 101 + (minutes - 1) * .1,
        'volume': 3 * minutes,
        'available_at_ms': minutes * 60000, 'watermark_ms': minutes * 60000,
    }
    assert snapshot['rows'][-1]['event_end_ms'] == selection['end_ms']
    assert 'REPEATABLE READ READ ONLY' in conn.calls[0][0]
    rows.pop()
    with pytest.raises(ValueError, match='SNAPSHOT_REVISIONS'):
        gateway.pinned_history(request)


def test_pinned_rollup_refuses_partial_unknown_or_synthetic_input_before_db(monkeypatch):
    import sys
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture

    _, selection, catalog, _ = snapshot_fixture(60)
    monkeypatch.setattr(gateway, '_snapshot_catalog', lambda: catalog)
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(
        connect=lambda *a, **k: pytest.fail('bad rollup must not access database')))
    request = dict(selection, schema='grid.history.selection.v2', timeframe='5m')
    for change, error in [
        ({'timeframe': '4h'}, 'timeframe'),
        ({'start_ms': 60000}, 'incomplete'),
        ({'end_ms': 59 * 60000}, 'incomplete'),
        ({'snapshot_id': 'f' * 64}, 'not provisioned'),
        ({}, 'historical source required'),
    ]:
        with pytest.raises(ValueError, match=error):
            gateway.pinned_history(dict(request, **change))


def _multipin_history(timeframe, start, page_sizes):
    from test_history_export import fixture
    from grid.history_export_v11 import export_records_v11
    from grid.provenance import digest

    end = start + sum(page_sizes) * 60000
    cursor = start
    catalog, raw_pages = {}, {}
    for size in page_sizes:
        rows, request, trust = fixture(size)
        receipts = {}
        for row in rows:
            receipt = trust['receipts'][row.pop('dataset_fingerprint')]
            for key in ('start_ms', 'end_ms', 'source_event_start_ms', 'source_event_end_ms'):
                row[key] += cursor
            revision = row['dataset_fingerprint'] = digest(row)
            receipt.update(fingerprint=revision, evidence_class='HISTORICAL',
                           available_at_ms=row['end_ms'] + 1, watermark_ms=row['end_ms'] + 1)
            receipts[revision] = receipt
        trust.update(evidence_class='HISTORICAL', receipts=receipts,
                     receipt_pins={key: digest(value) for key, value in receipts.items()})
        page_end = cursor + size * 60000
        request.update(start_ms=cursor, end_ms=page_end, as_of_ms=end, max_age_ms=end-cursor)
        envelope = export_records_v11(rows, request, trust)
        entry = dict(request=request, trust=trust, revisions=list(receipts),
                     dataset_id=envelope['dataset_id'], dataset_fingerprint=envelope['dataset_fingerprint'])
        catalog[digest(entry)] = entry
        raw_pages[cursor] = rows
        cursor = page_end
    selection = dict(schema='grid.history.selection.v3', timeframe=timeframe, snapshot_ids=list(catalog),
                     venue='bybit', market_type='linear', symbol='BTCUSDT', start_ms=start, end_ms=end)
    return selection, catalog, raw_pages


def test_pinned_v4_disposable_pg18_exact_receipt_and_tampering(monkeypatch):
    import os
    from contextlib import contextmanager
    from grid.provenance import digest

    dsn = os.environ.get('TERMINAN_DISPOSABLE_PG18_DSN')
    if not dsn:
        pytest.skip('explicit disposable PostgreSQL 18 DSN required')
    import psycopg
    from psycopg.types.json import Jsonb

    request, catalog, raw = _multipin_history('1h', 0, [35, 85])
    request['schema'] = 'grid.history.selection.v4'
    rows = [(row['dataset_fingerprint'], row['symbol'], row['start_ms'], Jsonb(row))
            for page in raw.values() for row in page]
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert 180000 <= conn.info.server_version < 190000
        conn.execute('CREATE TEMP TABLE provenance_minutes ('
                     'fingerprint text PRIMARY KEY, symbol text, start_ms bigint, record jsonb)')
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO provenance_minutes VALUES (%s, %s, %s, %s)', rows)

        @contextmanager
        def read_connection():
            with conn.transaction():
                yield conn
                assert conn.execute('SHOW transaction_read_only').fetchone() == ('on',)
                assert conn.execute('SHOW transaction_isolation').fetchone() == ('repeatable read',)

        monkeypatch.setattr(gateway, '_snapshot_catalog', lambda **_: catalog)
        monkeypatch.setattr(gateway, '_history_connection', read_connection)
        first = gateway.pinned_history(request)
        assert first == gateway.pinned_history(request)
        assert first['schema'] == 'grid.history.snapshot.response.v4'
        assert first['source_authentication'] == 'EXTERNAL_NOT_INDEPENDENTLY_VERIFIED'
        snapshot = first['snapshot']
        assert snapshot['schema'] == 'grid.history.rollup.v3'
        assert [row['event_start_ms'] for row in snapshot['rows']] == [0, 3600000]
        assert [row['volume'] for row in snapshot['rows']] == [180, 180]
        assert snapshot['dataset_fingerprint'] == V4_TWO_HOUR_FIXTURE_PIN == digest({
            key: value for key, value in snapshot.items() if key != 'dataset_fingerprint'
        })
        conn.execute("UPDATE pg_temp.provenance_minutes SET record = record || '{\"symbol\":\"ETHUSDT\"}' "
                     "WHERE start_ms = 3600000")
        with pytest.raises(ValueError, match='INTEGRITY'):
            gateway.pinned_history(request)
        original = next(row for page in raw.values() for row in page if row['start_ms'] == 3600000)
        conn.execute('UPDATE pg_temp.provenance_minutes SET record = %s WHERE start_ms = %s',
                     (Jsonb(original), original['start_ms']))
        assert gateway.pinned_history(request) == first


@pytest.mark.parametrize('version,timeframe,start,pages,width', [
    ('v3', '1h', 0, [60], 60), ('v3', '4h', 0, [120, 120], 240),
    ('v3', '1d', 0, [1440], 1440), ('v3', '1w', 4 * 86400000, [1680] * 6, 10080),
    ('v4', '1h', 0, [35, 85], 60), ('v4', '4h', 0, [100, 200, 180], 240),
    ('v4', '1d', 0, [1200, 1680], 1440), ('v4', '1w', 4 * 86400000, [1680] * 12, 10080),
])
def test_pinned_multipin_candle_reuses_exact_pages(monkeypatch, version, timeframe, start, pages, width):
    from test_history_snapshot import Connection
    from grid.provenance import canonical, digest

    request, catalog, raw_pages = _multipin_history(timeframe, start, pages)
    request['schema'] = f'grid.history.selection.{version}'
    cap = (16 if version == 'v4' else 8) * 1024 * 1024
    assert len(canonical(catalog)) <= cap

    class PagedConnection(Connection):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if params:
                self.rows = raw_pages[params[1]]

    conn = PagedConnection([])
    def load_catalog(max_bytes=8388608):
        assert max_bytes == cap
        return catalog
    monkeypatch.setattr(gateway, '_snapshot_catalog', load_catalog)
    monkeypatch.setattr(gateway, '_history_connection', lambda: conn)
    result = gateway.pinned_history(request)
    assert result['schema'] == f'grid.history.snapshot.response.{version}'
    assert result['source_authentication'] == 'EXTERNAL_NOT_INDEPENDENTLY_VERIFIED'
    assert result['read_only'] and not result['execution_authority'] and not result['trading_authorized']
    snapshot = result['snapshot']
    assert snapshot['schema'] == ('grid.history.rollup.v3' if version == 'v4' else 'grid.history.rollup.v2')
    assert [p['snapshot_id'] for p in snapshot['parents']] == request['snapshot_ids']
    assert snapshot['dataset_fingerprint'] == digest({k: v for k, v in snapshot.items() if k != 'dataset_fingerprint'})
    if version == 'v4' and timeframe == '1h':
        assert snapshot['dataset_fingerprint'] == V4_TWO_HOUR_FIXTURE_PIN
    flat = [minute for page in raw_pages.values() for minute in page]
    assert len(snapshot['rows']) == len(flat) // width
    for i, row in enumerate(snapshot['rows']):
        window = flat[i*width:(i+1)*width]
        assert row['event_start_ms'] == start + i*width*60000
        assert row['event_end_ms'] == row['available_at_ms'] == row['watermark_ms'] == start + (i+1)*width*60000
        assert (row['open'], row['high'], row['low'], row['close'], row['volume']) == (
            window[0]['candle']['open'], max(x['candle']['high'] for x in window),
            min(x['candle']['low'] for x in window), window[-1]['candle']['close'], width*3)
    assert sum('SET TRANSACTION' in sql for sql, _ in conn.calls) == 1
    assert sum('fingerprint = ANY(%s)' in sql for sql, _ in conn.calls) == len(pages)
    raw_pages[max(raw_pages)].pop()
    with pytest.raises(ValueError, match='SNAPSHOT_REVISIONS'):
        gateway.pinned_history(request)


@pytest.mark.parametrize('version', ['v3', 'v4'])
def test_pinned_multipin_refuses_incomplete_or_mixed_source_before_db(monkeypatch, version):
    from grid.provenance import digest

    selection, catalog, _ = _multipin_history('4h', 0, [120, 120])
    selection['schema'] = f'grid.history.selection.{version}'
    left, right = selection['snapshot_ids']
    untrusted = catalog[right].copy()
    untrusted['trust'] = dict(untrusted['trust'], epoch='another-epoch')
    alternate = digest(untrusted)
    catalog[alternate] = untrusted
    monkeypatch.setattr(gateway, '_snapshot_catalog', lambda **_: catalog)
    monkeypatch.setattr(gateway, '_history_connection', lambda: pytest.fail('invalid page set must not touch DB'))
    for change, reason in [
        ({'start_ms': 60000, 'end_ms': 241*60000}, 'ALIGNMENT'),
        ({'snapshot_ids': [right, left]}, 'CONTINUITY'),
        ({'snapshot_ids': [left]}, 'CONTINUITY'),
        ({'snapshot_ids': [left, left]}, 'PINS'),
        ({'snapshot_ids': [f'{i:064x}' for i in range(17)]}, 'PINS'),
        ({'snapshot_ids': [left, alternate]}, 'LINEAGE'),
        ({'end_ms': 240 * 60000 * 33}, 'ALIGNMENT'),
        ({'symbol': 'ETHUSDT'}, 'IDENTITY'),
    ]:
        with pytest.raises(ValueError, match=reason):
            gateway.pinned_history(dict(selection, **change))


def test_pinned_history_rejects_unprovisioned_or_changed_selection_without_sql(monkeypatch):
    import sys
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture
    rows, selection, catalog, expected=snapshot_fixture()
    monkeypatch.setattr(gateway,'_snapshot_catalog',lambda:catalog)
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(
        connect=lambda *a,**k:pytest.fail('invalid snapshot must not touch database')))
    for change in ({'snapshot_id':'f'*64},{'symbol':'ETHUSDT'},
                   {'start_ms':True},{'end_ms':120000001},
                   {'schema':'untrusted'}, {'unexpected':1}):
        req=dict(selection)
        req.update(change)
        with pytest.raises(ValueError):
            gateway.pinned_history(req)


def test_pinned_history_catalog_rejects_symlink_world_writable_and_duplicate_keys(monkeypatch,tmp_path):
    import os
    from test_history_snapshot import snapshot_fixture
    rows, selection, catalog, expected=snapshot_fixture()
    p=tmp_path/'trusted.json'
    monkeypatch.setenv('GRID_PINNED_HISTORY_CATALOG',str(p))
    p.write_text('{"x":1,"x":2}',encoding='utf-8')
    p.chmod(0o600)
    if os.name=='nt':
        # Portable mode bits cannot establish an NTFS DACL trust boundary.
        # This is an explicit Windows NO_GO gate, not a skipped test.
        with pytest.raises(RuntimeError,match='WINDOWS_CATALOG_ACL_NOT_QUALIFIED'):
            gateway._snapshot_catalog()
        return
    with pytest.raises(ValueError,match='duplicate'):
        gateway._snapshot_catalog()
    p.write_text('{"x":1}',encoding='utf-8')
    if os.name!='nt':
        p.chmod(0o666)
        with pytest.raises(RuntimeError):
            gateway._snapshot_catalog()
        p.chmod(0o600)
    alias=tmp_path/'alias.json'
    try:alias.symlink_to(p)
    except (OSError,NotImplementedError):
        return
    monkeypatch.setenv('GRID_PINNED_HISTORY_CATALOG',str(alias))
    with pytest.raises(RuntimeError):
        gateway._snapshot_catalog()


def test_pinned_snapshot_post_http_requires_valid_explicit_small_json(monkeypatch):
    import io,json
    from types import SimpleNamespace
    def request(path,body,headers):
        handler=object.__new__(gateway.Handler)
        handler.path=path
        handler.headers=headers
        handler.rfile=io.BytesIO(body)
        handler.wfile=io.BytesIO()
        handler.connection=SimpleNamespace(settimeout=lambda _:None)
        statuses=[]
        handler.send_response=lambda status:statuses.append(status)
        handler.send_header=lambda *args:None
        handler.end_headers=lambda:None
        handler.send_error=lambda status:statuses.append(status)
        handler.do_POST()
        return statuses,json.loads(handler.wfile.getvalue() or b'{}')
    monkeypatch.setattr(gateway,'pinned_history',lambda *a:pytest.fail('invalid request reached trust path'))
    cases=[
        (b'{}',{'Content-Length':'2','Content-Type':'text/plain'}),
        (b'{}',{'Content-Length':'0','Content-Type':'application/json'}),
        (b'{"a":1,"a":2}',{'Content-Length':'13','Content-Type':'application/json'}),
        (b'{}',{'Content-Length':'2','Content-Type':'application/json','Transfer-Encoding':'chunked'}),
    ]
    for payload, headers in cases:
        statuses,response=request('/internal/v1/history/snapshots/read',payload,headers)
        assert statuses==[400]
        assert response['status']=='UNAVAILABLE'



def test_pinned_history_rejects_query_in_post_url(monkeypatch):
    import io, json
    from types import SimpleNamespace
    monkeypatch.setattr(gateway,'pinned_history',
                        lambda *args:pytest.fail('query must fail before snapshot dispatch'))
    body=b'{}'
    handler=object.__new__(gateway.Handler)
    handler.path='/internal/v1/history/snapshots/read?selection=other'
    handler.headers={'Content-Length':str(len(body)),'Content-Type':'application/json'}
    handler.rfile=io.BytesIO(body)
    handler.wfile=io.BytesIO()
    handler.connection=SimpleNamespace(settimeout=lambda _:None)
    statuses=[]
    handler.send_response=lambda code:statuses.append(code)
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    handler.do_POST()
    assert statuses==[400]
    assert json.loads(handler.wfile.getvalue())['reason']=='INVALID_SNAPSHOT_REQUEST'


@pytest.mark.parametrize('version', ['v1', 'v2', 'v3', 'v4'])
def test_pinned_snapshot_post_invokes_existing_read_only_history(monkeypatch, version):
    import io,json
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture
    rows, selection, catalog, expected=snapshot_fixture()
    if version != 'v1':
        selection = dict(selection, schema=f'grid.history.selection.{version}', timeframe='1h')
    if version in ('v3', 'v4'):
        selection['snapshot_ids'] = [selection.pop('snapshot_id')]
    observed=[]
    def selected(req):
        observed.append(req)
        return {'status':'PINNED_HISTORICAL_SOURCE_UNATTESTED',
                'snapshot':expected,'execution_authority':False}
    monkeypatch.setattr(gateway,'pinned_history',selected)
    payload=json.dumps(selection).encode('utf-8')
    handler=object.__new__(gateway.Handler)
    handler.path='/internal/v1/history/snapshots/read'
    handler.headers={'Content-Length':str(len(payload)),'Content-Type':'application/json'}
    handler.rfile=io.BytesIO(payload);handler.wfile=io.BytesIO()
    handler.connection=SimpleNamespace(settimeout=lambda _:None)
    handler._deadline = object()
    deadlines = []
    handler._arm_deadline = deadlines.append
    statuses=[]
    handler.send_response=lambda status:statuses.append(status)
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    handler.do_POST()
    assert statuses==[200]
    assert observed==[selection]
    assert deadlines == {'v3': [40], 'v4': [70]}.get(version, [])
    assert json.loads(handler.wfile.getvalue())['snapshot']==expected
