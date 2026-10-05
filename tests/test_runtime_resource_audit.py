from pathlib import Path


def test_runtime_wal_replay_is_streaming():
    for name in ("grid/storage.py","grid/micro_event_storage.py"):
        s=Path(name).read_text()
        assert ".iter_recover()" in s
        assert "pending=self.spool.recover()" not in s


def test_microstructure_receive_queue_is_bounded():
    s=Path("grid/microstructure.py").read_text()
    assert "max_queue=2000" in s
    assert "max_queue=50000" not in s


def test_logs_bound_large_records_and_keep_resource_fields():
    s=Path("grid/logging_setup.py").read_text()
    assert "MAX_LOG_MESSAGE" in s and "MAX_LOG_EXCEPTION" in s
    assert '"process_rss"' in s
    assert '"queue_ratio"' in s


def test_derived_watermarks_are_batched():
    s=Path("grid/derived_pipeline.py").read_text()
    assert "set_consumer_watermarks" in s
    assert "await set_consumer_watermark(" not in s


def test_schema_audit_covers_hot_tables():
    s=Path("grid/schema_audit.py").read_text()
    for table in ("candles_1m","footprint_1m","market_events","market_features_1m","ml_jobs"):
        assert f'"{table}"' in s
