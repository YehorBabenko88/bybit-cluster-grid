import asyncio
import json
import math
from types import SimpleNamespace

import pytest

from grid.scientific_geometry import OnlineStandardizer,ScientificGeometryEngine,polynomial_terms3
from grid.scientific_discovery import ScientificDiscoveryEngine,DEFAULT_FEATURES

def row(k=1.0):
    return {n:(i+1)*k/100 for i,n in enumerate(DEFAULT_FEATURES)}

def test_standardizer_is_past_only():
    s=OnlineStandardizer()
    assert s.transform_then_update([100,200])==[0.0,0.0]
    z=s.transform_then_update([101,202])
    assert z==[0.0,0.0]
    z=s.transform_then_update([100,200])
    assert all(math.isfinite(v) for v in z)

def test_projection_is_3d_but_full_vector_is_preserved():
    e=ScientificGeometryEngine(DEFAULT_FEATURES)
    p=e.ingest("BTC",1,row())
    assert len(p.vector)==len(DEFAULT_FEATURES) and len(p.projection3d)==3

def test_polynomial_basis_contains_cubic_geometry():
    assert len(polynomial_terms3((1,2,3),3))==20

def test_discovery_rejects_time_reversal_and_bad_quality():
    e=ScientificDiscoveryEngine()
    assert e.ingest_feature_row("BTC",1000,row())["accepted"]
    assert not e.ingest_feature_row("BTC",999,row())["accepted"]
    assert not e.ingest_feature_row("ETH",1000,row(),quality="DEGRADED")["accepted"]

def test_discovery_combines_geometry_stochastic_and_regime_diagnostics():
    e=ScientificDiscoveryEngine()
    out=None
    for i in range(40):out=e.ingest_feature_row("BTC",i+1,row(1+i/100))
    d=out["diagnostics"]
    assert "tortuosity" in d and "return_lag1_acf" in d and "volatility_regime" in d


def test_geometry_learning_state_is_isolated_per_symbol():
    e=ScientificGeometryEngine(DEFAULT_FEATURES)
    e.ingest("BTC",1,row(1))
    e.ingest("BTC",2,row(10))
    eth=e.ingest("ETH",1,row(100))
    assert eth.projection3d==(0.0,0.0,0.0)

def test_geometry_bucket_waits_for_frozen_projection():
    from grid.scientific_orchestrator import _geometry_bucket
    assert _geometry_bucket({"projection_ready":False,"tortuosity":10})=="WARMUP"
    assert _geometry_bucket({"projection_ready":True,"tortuosity":1,"mean_turn_cos":.8,
                             "surface_cubic":{"ready":False},"cubic_fit_gain":None})=="PERSISTENT"


@pytest.mark.parametrize('path', [
    '/strategy/plugins', '/strategy/jobs', '/scientific/status',
    '/scientific/simulations', '/scientific/history/import',
])
def test_grid_coordinator_rejects_legacy_trade_and_research_owners(path):
    from grid import coordinator

    async def next_handler(_request):
        pytest.fail('legacy owner handler must never execute')

    request = SimpleNamespace(url=SimpleNamespace(path=path))
    result = asyncio.run(coordinator.coordinated_request_guard(request, next_handler))
    assert result.status_code == 503
    assert json.loads(result.body) == {'reason': 'OWNER_MIGRATION_REQUIRED'}
