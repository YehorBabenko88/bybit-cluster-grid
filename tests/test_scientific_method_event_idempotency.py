from pathlib import Path


def test_method_event_idempotency_migration_and_insert():
    migration=Path("grid/migrations.py").read_text(encoding="utf-8")
    registry=Path("grid/scientific_method_registry.py").read_text(encoding="utf-8")
    assert '(46,"scientific_method_event_idempotency"' in migration
    assert "ADD COLUMN IF NOT EXISTS source_event_id bigint" in migration
    assert "ON scientific_method_events(method_key,source_event_id)" in migration
    assert "WHERE source_event_id IS NOT NULL" in migration
    assert "ON CONFLICT (method_key,source_event_id)" in registry
    assert 'event.get("source_event_id")' in registry
