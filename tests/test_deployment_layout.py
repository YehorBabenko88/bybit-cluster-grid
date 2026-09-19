import pathlib

def test_required_deployment_files_exist():
    required=[
        "installer/bootstrap.ps1",
        "installer/discover.ps1",
        "installer/install.ps1",
        "installer/uninstall.ps1",
        "installer/preflight.ps1",
        "requirements.txt",
        "run_worker.py",
        "run_coordinator.py",
    ]
    missing=[p for p in required if not pathlib.Path(p).exists()]
    assert not missing, f"missing deployment files: {missing}"
