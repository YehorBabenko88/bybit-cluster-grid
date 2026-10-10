from pathlib import Path


def test_ml_requirements_include_both_tree_backends():
    req=Path("requirements-ml.txt").read_text(encoding="utf-8").lower()
    assert "xgboost" in req
    assert "lightgbm" in req
    assert "scikit-learn" in req


def test_ml_bootstrap_is_role_aware_and_repairable():
    s=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '$Mode -in @("CONTROL","PILOT")' in s
    assert "ml-requirements.sha256" in s
    assert "ml-bootstrap.json" in s
    assert '--retries 8 --timeout 60 --prefer-binary' in s
    assert "import numpy,scipy,sklearn,joblib,xgboost,lightgbm" in s
    assert "XGBRegressor" in s
    assert "LGBMRegressor" in s
    assert 'status="failed"' in s


def test_main_bootstrap_invokes_ml_bootstrap_and_auto_pilot_rechecks():
    s=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert s.count("bootstrap-ml.ps1")>=2
    assert 'if($AgentMode -eq "PILOT")' in s
    assert "Grid ML runtime bootstrap failed" in s


def test_nodes_advertise_ml_runtime_and_dispatcher_requires_it():
    resources=Path("grid/resources.py").read_text(encoding="utf-8")
    dispatcher=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    assert '"ml_runtime_ready":ml_runtime_ready()' in resources
    assert 'if candidate["job_type"] in ("train","evaluate")' in dispatcher
    assert 'v.get("ml_runtime_ready") is True' in dispatcher


def test_install_state_persists_authorized_mode_separately_from_repair_kind():
    script = Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert 'authorized_agent_mode=$AgentMode' in script
    assert 'mode=$Mode;status="installed"' in script
    assert 'if($Enrollment.install_mode -notin @("PILOT","NORMAL"))' in script


def test_ml_bootstrap_recreates_missing_ready_journal_without_pip():
    script = Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert 'if(!(Test-Path -LiteralPath $Python))' in script
    healthy = script.split('if(!$Need){', 1)[1].split('exit 0', 1)[0]
    assert 'status="ready"' in healthy
    assert 'Write-MLJournal' in healthy
    assert '-m pip install' not in healthy


def test_windows_bundle_contains_ml_requirements_and_checks_presence():
    workflow = Path(".github/workflows/windows-bundle.yml").read_text(encoding="utf-8")
    assert "run_worker.py,run_coordinator.py,requirements.txt,requirements-ml.txt" in workflow
    assert 'if(!(Test-Path (Join-Path $bundle "requirements-ml.txt")))' in workflow
    assert '      - "requirements-ml.txt"' in workflow


def test_pilot_and_control_preflight_fail_without_ml_requirements():
    preflight = Path("installer/preflight.ps1").read_text(encoding="utf-8")
    assert '$Mode -in @("CONTROL","PILOT")' in preflight
    assert 'Join-Path $ReleaseDir "requirements-ml.txt"' in preflight
    assert 'throw "ML requirements missing for $Mode release:' in preflight


def test_ml_claim_transport_failure_does_not_terminate_poller():
    worker = Path("grid/ml_agent_worker.py").read_text(encoding="utf-8")
    loop = worker.split("async def ml_agent_loop(", 1)[1]
    assert "try:\n            job=await client.claim()" in loop
    assert "except asyncio.CancelledError:\n            raise" in loop
    assert "except Exception:" in loop
    assert "continue" in loop


def test_cached_ml_runtime_runs_native_smoke_before_ready():
    script = Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    cached = script.split("if(!$Need){", 2)[2].split("if(!$Need){", 1)[0]
    assert "XGBRegressor" in cached
    assert "LGBMRegressor" in cached
    assert "$Need=$true" in cached


def test_ml_isolation_uses_dedicated_venv_and_compute_interpreter():
    bootstrap=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    main=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    agent=Path("grid/ml_agent_worker.py").read_text(encoding="utf-8")
    resources=Path("grid/resources.py").read_text(encoding="utf-8")
    assert '$MLVenv=Join-Path $RuntimeRoot "ml-venv"' in bootstrap
    assert '-r $CoreReq -r $Req' in bootstrap
    assert "-BasePython $BasePython" in main
    assert '"ml-venv"/"Scripts"/"python.exe"' in agent
    assert '"ml-venv","Scripts","python.exe"' in resources


def test_windows_ml_job_object_fail_closed():
    supervisor=Path("grid/ml_process_supervisor.py").read_text(encoding="utf-8")
    windows=Path("grid/ml_windows_job.py").read_text(encoding="utf-8")
    assert "job_object=WindowsJob(proc.pid, resume_primary_thread=True)" in supervisor
    assert "await terminate_process_tree(proc,grace_seconds)" in supervisor
    assert "job_object.close()" in supervisor
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in windows
    assert "AssignProcessToJobObject" in windows


def test_cached_ml_environment_validates_protocol_dependencies():
    script = Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert "import aiohttp,asyncpg,psutil,pydantic,httpx,websockets,numpy,scipy,sklearn,joblib,xgboost,lightgbm" in script


def test_missing_ml_runtime_readiness_is_cached():
    script = Path("grid/resources.py").read_text(encoding="utf-8")
    assert 'if os.path.isfile(python) and os.path.isfile(journal):' in script
    assert '_ML_READY_CACHE.update(at=time.monotonic(),value=ready,running=False)' in script
    assert 'threading.Thread(target=_probe_ml_runtime' in script
    assert 'if _ML_READY_CACHE["running"]:' in script


def test_ml_bootstrap_repairs_corrupted_interpreter_and_fails_closed():
    script=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert 'assert sys.prefix != sys.base_prefix' in script
    assert 'Remove-Item -LiteralPath $MLVenv -Recurse -Force' in script
    assert 'status="installing"' in script
    assert 'status="failed"' in script


def test_recreated_ml_environment_always_reinstalls_dependencies():
    script=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '$Need=($Hash -ne $Old) -or $Recreate' in script
    assert 'if($Recreate){' in script


def test_ml_journal_is_atomically_replaced():
    script=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '[System.IO.File]::Move($tmp,$Journal,$true)' in script
    assert 'ValueFromPipeline=$true' in script
    assert 'Set-Content -Encoding UTF8 $Journal' not in script


def test_ml_bootstrap_recreates_venv_if_pip_is_broken():
    script=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '& $MLPython -m pip --version' in script
    assert 'if($LASTEXITCODE -ne 0){$Recreate=$true}' in script
    workflow=Path(".github/workflows/windows-bundle.yml").read_text(encoding="utf-8")
    assert 'Repair ML venv with missing pip on Windows' in workflow


def test_interrupted_ml_bootstrap_forces_dependency_repair():
    script=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '$PreviousReady=($PreviousJournal.status -eq "ready")' in script
    assert '$Need=($Hash -ne $Old) -or $Recreate -or !$PreviousReady' in script
    assert 'Write-MLJournal' in script
