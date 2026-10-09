from grid.migrations import MIGRATIONS


def test_production_evaluation_guard_migration_exists():
    migrations = {version: statements for version, _, statements in MIGRATIONS}
    assert 45 in migrations
    sql = "\n".join(migrations[45])
    assert "BEFORE INSERT OR UPDATE OR DELETE" in sql
    assert "FROM model_registry" in sql
    assert "FOR UPDATE" in sql
    assert "model_status='PRODUCTION'" in sql
    assert "RAISE EXCEPTION" in sql
    assert "TG_OP='DELETE'" in sql
