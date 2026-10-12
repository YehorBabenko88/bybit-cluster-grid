from pathlib import Path


def test_delayed_heartbeat_does_not_renew_expired_assignments():
    source=Path("grid/worker.py").read_text(encoding="utf-8")
    received=source.index("response_received_at=time.monotonic()")
    lock=source.index("async with self.assignment_lock:",received)
    reject=source.index("if response_age >= max(1.0,3.0*settings.heartbeat_seconds):",lock)
    renewal=source.index("self.last_assignment_heartbeat=time.monotonic()",lock)
    assert received < lock < reject < renewal
    assert "continue" in source[reject:renewal]
    assert 'extra={"event":"stale_control_heartbeat"' in source[reject:renewal]
