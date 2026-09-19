from pathlib import Path

BOOT=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")

def test_runtime_is_grid_owned():
    assert '$OwnedPython=Join-Path $RuntimeRoot' in BOOT
    assert '"python\\\\python.exe"' in BOOT
    assert 'Grid-owned Python runtime is missing' in BOOT
    assert 'Get-Command python.exe' not in BOOT

def test_damaged_venv_is_rebuilt():
    assert '$RebuildVenv=$true' in BOOT
    assert 'Remove-Item -Recurse -Force $Venv' in BOOT
    assert '-m venv $Venv' in BOOT

def test_dependencies_use_fingerprint_and_import_repair():
    assert 'requirements.sha256' in BOOT
    assert 'Get-FileHash -Algorithm SHA256' in BOOT
    assert 'import aiohttp,asyncpg,psutil,websockets,pydantic,fastapi,httpx' in BOOT

def test_failed_install_rolls_bootstrap_back():
    assert 'status="failed"' in BOOT
    assert 'bootstrap.previous' in BOOT
    assert 'Bootstrap rolled back to previous release.' in BOOT
