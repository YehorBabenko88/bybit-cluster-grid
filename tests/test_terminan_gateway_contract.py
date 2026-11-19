import pytest
from grid import terminan_gateway as gateway


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
