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


def test_pinned_snapshot_post_invokes_existing_read_only_history(monkeypatch):
    import io,json
    from types import SimpleNamespace
    from test_history_snapshot import snapshot_fixture
    rows, selection, catalog, expected=snapshot_fixture()
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
    statuses=[]
    handler.send_response=lambda status:statuses.append(status)
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    handler.do_POST()
    assert statuses==[200]
    assert observed==[selection]
    assert json.loads(handler.wfile.getvalue())['snapshot']==expected

@pytest.mark.parametrize('path', [
    '/strategy/plugins', '/strategy/jobs', '/scientific/status',
    '/scientific/simulations', '/scientific/history/import',
])
def test_grid_coordinator_rejects_legacy_trade_and_research_owners(path):
    import asyncio
    from types import SimpleNamespace
    from grid import coordinator
    called = []
    async def next_handler(_request):
        called.append(True)
        pytest.fail('legacy owner handler must never execute')
    request = SimpleNamespace(url=SimpleNamespace(path=path))
    result = asyncio.run(coordinator.coordinated_request_guard(request, next_handler))
    assert result.status_code == 503
    import json
    assert json.loads(result.body) == {'reason': 'OWNER_MIGRATION_REQUIRED'}
    assert called == []
