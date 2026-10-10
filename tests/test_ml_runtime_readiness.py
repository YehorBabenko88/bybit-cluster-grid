import time
from unittest.mock import patch

from grid import resources


def test_ml_readiness_probe_does_not_block_heartbeat():
    """A slow ML import must not hold up the caller's heartbeat."""
    resources._ML_READY_CACHE.update(at=0.0, value=False, running=False)

    def slow_probe(python, journal):
        time.sleep(0.5)
        with resources._ML_READY_LOCK:
            resources._ML_READY_CACHE.update(at=time.monotonic(), value=True, running=False)

    try:
        with patch.object(resources, "_probe_ml_runtime", slow_probe):
            started=time.monotonic()
            assert resources.ml_runtime_ready() is False
            assert time.monotonic()-started < 0.3
            assert resources.ml_runtime_ready() is False
            deadline=time.monotonic()+3
            while resources._ML_READY_CACHE["running"] and time.monotonic()<deadline:
                time.sleep(0.02)
            assert resources.ml_runtime_ready() is True
    finally:
        with resources._ML_READY_LOCK:
            resources._ML_READY_CACHE.update(at=0.0, value=False, running=False)


def test_ml_probe_missing_files_fails_closed(tmp_path):
    resources._ML_READY_CACHE.update(at=0.0,value=True,running=True)
    resources._probe_ml_runtime(str(tmp_path/"missing-python"),str(tmp_path/"missing-journal"))
    assert resources._ML_READY_CACHE["value"] is False
    assert resources._ML_READY_CACHE["running"] is False


def test_ml_readiness_rejects_failed_journal(tmp_path):
    import json
    python=tmp_path/"python.exe"
    journal=tmp_path/"ml-bootstrap.json"
    python.write_text("not executable")
    journal.write_text(json.dumps({"status":"failed"}))
    with patch.object(resources.subprocess,"run",side_effect=AssertionError("must not run ML")):
        resources._probe_ml_runtime(str(python),str(journal))
    assert resources._ML_READY_CACHE["value"] is False


def test_ml_readiness_rejects_corrupt_journal(tmp_path):
    python=tmp_path/"python.exe"
    journal=tmp_path/"ml-bootstrap.json"
    python.write_text("not executable")
    journal.write_text("{broken json")
    resources._probe_ml_runtime(str(python),str(journal))
    assert resources._ML_READY_CACHE["value"] is False


def test_ml_readiness_invalidates_ready_cache_on_journal_change(tmp_path):
    import json
    root=tmp_path/"BybitClusterGrid"/"runtime"
    root.mkdir(parents=True)
    journal=root/"ml-bootstrap.json"
    journal.write_text(json.dumps({"status":"ready"}))
    stat=journal.stat()
    with patch.dict(resources.os.environ,{"ProgramData":str(tmp_path)}):
        resources._ML_READY_CACHE.update(at=time.monotonic(),value=True,running=False,
            journal_signature=(stat.st_mtime_ns,stat.st_size))
        journal.write_text(json.dumps({"status":"installing"}))
        assert resources.ml_runtime_ready() is False
        deadline=time.monotonic()+3
        while resources._ML_READY_CACHE["running"] and time.monotonic()<deadline:
            time.sleep(.02)
        assert resources._ML_READY_CACHE["value"] is False
    resources._ML_READY_CACHE.update(at=0.0,value=False,running=False,journal_signature=None)
