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


def test_grid_coordinator_does_not_start_or_expose_scientific_strategy_engines():
    """Grid retains market-data delivery, not a second strategy or Math backend."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "grid" / "coordinator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and
                    isinstance(decorator.func, ast.Attribute) and
                    isinstance(decorator.func.value, ast.Name) and
                    decorator.func.value.id == "app" and
                    decorator.func.attr in ("get", "post", "put", "delete") and
                    decorator.args and isinstance(decorator.args[0], ast.Constant)):
                routes.append(decorator.args[0].value)

    assert "/ingest/minute" in routes
    assert "/ingest/event" in routes
    assert not any(route.startswith(("/strategy/", "/scientific/"))
                   for route in routes)
    # The existing request middleware still denies stale external callers.
    middleware = next(node for node in tree.body if
                      isinstance(node, ast.AsyncFunctionDef) and
                      node.name == "coordinated_request_guard")
    body = ast.get_source_segment(source, middleware)
    assert "OWNER_MIGRATION_REQUIRED" in body
    assert "'/strategy/'" in body and "'/scientific/'" in body

    forbidden = {"ScientificResearchService", "scientific_service",
                 "ensure_strategy_schema", "ensure_plugin_schema",
                 "register_plugin", "list_plugins", "submit_job"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not forbidden.intersection(names)
    # Do not resurrect scientific, strategy or simulation table migrations
    # inside the Grid controller's startup/readiness path.
    imports = [node.module for node in tree.body
               if isinstance(node, ast.ImportFrom)]
    assert "strategy_jobs" not in imports
    assert "strategy_plugins" not in imports
    assert "scientific_service" not in imports
