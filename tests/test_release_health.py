from grid.update_protocol import release_health_ok

def good(**overrides):
    x={
      "integrity_ok":True,"pressure_state":"NORMAL","db_write_failures":0,
      "db_write_failures_recent":0,
      "db_queue_ratio":0.0,"db_spool_ratio":0.0,
    }
    x.update(overrides)
    return x

def test_release_health_accepts_clean_infra_only_heartbeat():
    ok,reason=release_health_ok(good(runtime_state="INFRA_ONLY"))
    assert ok and reason is None


def test_legacy_heartbeat_missing_interval_failure_counter_stays_rejected():
    heartbeat=good(runtime_state='INFRA_ONLY')
    heartbeat.pop('db_write_failures_recent')
    assert release_health_ok(heartbeat)==(False,'db_write_failures_recent_missing')

def test_release_health_rejects_integrity_failure():
    assert release_health_ok(good(integrity_ok=False))[0] is False

def test_release_health_rejects_critical_pressure():
    assert release_health_ok(good(pressure_state="CRITICAL"))[0] is False

def test_release_health_rejects_db_failures_and_backpressure():
    assert release_health_ok(good(db_write_failures_recent=1))[0] is False
    assert release_health_ok(good(db_queue_ratio=.8))[0] is False
    assert release_health_ok(good(db_spool_ratio=.9))[0] is False
