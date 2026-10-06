from pathlib import Path


def test_coordinator_exposes_health_endpoint():
    src = Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in src
    assert 'await db.pool.fetchval("SELECT 1")' in src
    assert '"service": "Bybit Cluster Grid Coordinator"' in src
    assert 'raise HTTPException(503,"database not ready")' in src
