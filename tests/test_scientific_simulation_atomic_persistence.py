from pathlib import Path


def test_simulation_trades_and_completion_share_transaction():
    source = Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    start = source.index('        # Persist all trade rows')
    end = source.index('        return {"run_id":str(run_id),"status":status,', start)
    section = source[start:end]
    assert "async with self.pool.acquire() as conn:" in section
    assert "async with conn.transaction():" in section
    assert 'await conn.execute("""INSERT INTO scientific_simulation_trades(' in section
    assert 'await conn.execute("""UPDATE scientific_simulation_runs SET status=$2,' in section
    assert section.index("async with conn.transaction():") < section.index("INSERT INTO scientific_simulation_trades")
    assert section.index("INSERT INTO scientific_simulation_trades") < section.index("UPDATE scientific_simulation_runs SET status=$2")
