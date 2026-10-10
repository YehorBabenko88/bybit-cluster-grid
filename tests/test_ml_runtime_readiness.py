import os
import time
from unittest.mock import patch

from grid import resources


def test_ml_readiness_probe_does_not_block_heartbeat():
    """A slow ML import must not hold up the caller's heartbeat."""
    resources._ML_READY_CACHE.update(at=0.0, value=False, running=False)
    original = resources._probe_ml_runtime

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
