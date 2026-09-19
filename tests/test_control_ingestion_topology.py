from pathlib import Path

def test_worker_has_no_bybit_discovery_at_run_start():
    text=Path("grid/worker.py").read_text(encoding="utf-8")
    run=text.split("async def run(self):",1)[1]
    pre_heartbeat=run.split("await self.heartbeat()",1)[0]
    assert "linear_symbols(" not in pre_heartbeat
    assert "self.meta={}" in pre_heartbeat

def test_postgres_is_control_only_in_bootstrap():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert 'if($AgentMode -eq "CONTROL")' in text
    assert "PostgreSQL provisioning skipped" in text

def test_worker_is_dbless():
    text=Path("grid/worker.py").read_text(encoding="utf-8")
    run=text.split("async def run(self):",1)[1]
    assert "self.db=None" in run
    assert "prepare_database()" not in run.split("await self.heartbeat()",1)[0]

def test_ingestion_is_active_gated_and_authenticated():
    text=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert '@app.post("/ingest/minute")' in text
    assert "authenticate_agent(db.pool,x_node_id,x_node_credential)" in text
    assert 'gate["state"]!="ACTIVE"' in text
