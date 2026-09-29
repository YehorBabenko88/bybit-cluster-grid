from pathlib import Path


def test_update_schema_creates_rollout_nodes():
    source = Path("grid/update_protocol.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS rollout_nodes(" in source
    assert "PRIMARY KEY(version,node_id)" in source


def test_rollout_expiry_uses_bootstrapped_table():
    update_source = Path("grid/update_protocol.py").read_text(encoding="utf-8")
    rollout_source = Path("grid/rollout.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS rollout_nodes(" in update_source
    assert "async def expire_rollout_nodes(pool):" in rollout_source
    assert "UPDATE rollout_nodes SET status='rollback_pending'" in rollout_source
