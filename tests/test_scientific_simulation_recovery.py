from pathlib import Path


def test_abandoned_simulation_can_be_reclaimed_without_mixing_trades():
    source = Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert source.count("started_at < now() - interval '24 hours'") == 2
    assert "DELETE FROM scientific_simulation_trades WHERE run_id=$1" in source
    section = source[source.index("async with conn.transaction():"):]
    assert section.index("DELETE FROM scientific_simulation_trades") < section.index("INSERT INTO scientific_simulation_trades")
    assert section.index("INSERT INTO scientific_simulation_trades") < section.index("UPDATE scientific_simulation_runs SET status=$2")
