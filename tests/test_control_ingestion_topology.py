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
    assert "not await authenticate_agent(db.pool,x_node_id,x_node_credential)" in text
    assert 'gate["state"]!="ACTIVE"' in text

def test_coordinator_ingest_storage_has_module_lifecycle():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "grid"
        / "coordinator.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    module_names = set()

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_names.add(target.id)

    assert "ingest_storage" in module_names

    startup = next(
        node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "startup"
    )

    global_names = {
        name
        for node in startup.body
        if isinstance(node, ast.Global)
        for name in node.names
    }

    assert "db" in global_names
    assert "ingest_storage" in global_names

def test_coordinator_background_tasks_have_shutdown_lifecycle():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "grid"
        / "coordinator.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    module_names = set()
    functions = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_names.add(target.id)

        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            functions[node.name] = node

    assert "background_tasks" in module_names
    assert "startup" in functions
    assert "shutdown" in functions

    startup_source = ast.get_source_segment(
        source,
        functions["startup"],
    )
    shutdown_source = ast.get_source_segment(
        source,
        functions["shutdown"],
    )

    assert startup_source.count("asyncio.create_task(") >= 2
    assert "background_tasks" in startup_source

    assert "task.cancel()" in shutdown_source
    assert "asyncio.gather(" in shutdown_source
    assert "return_exceptions=True" in shutdown_source
    assert "background_tasks = []" in shutdown_source
    assert "ingest_storage = None" in shutdown_source
