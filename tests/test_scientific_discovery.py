import math
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

def test_control_wires_scientific_service_without_worker_dependency():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    st=Path("grid/storage.py").read_text(encoding="utf-8")
    assert "ScientificResearchService" in c
    assert "asyncio.create_task(scientific_service.run())" in c
    assert '@app.get("/scientific/status")' in c
    assert "self.scientific=None" in st
    assert "self.scientific.ingest_feature_row" in st
