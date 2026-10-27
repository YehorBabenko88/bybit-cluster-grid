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
