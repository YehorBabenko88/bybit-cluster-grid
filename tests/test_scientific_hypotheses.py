from grid.scientific_hypotheses import HypothesisSpec,Evidence,lifecycle

def spec():
    return HypothesisSpec("micro_geometry_consensus","delta+oi",5000,1,"v1",{"x":1})

def ev(key,symbol,regime,split,n=80,mean=3.0,hit=.6,cost=1.0):
    return Evidence(key,symbol,regime,split,n,mean,hit,cost)

def test_same_experiment_cannot_manufacture_replication():
    s=spec()
    rows=[ev("A","BTC","NORMAL","2026-W01"),ev("A","BTC","NORMAL","2026-W01",200)]
    assert lifecycle(s,rows)=="OBSERVED"

def test_independent_splits_replicate():
    s=spec()
    rows=[ev("A","BTC","NORMAL","W1"),ev("B","ETH","NORMAL","W2")]
    assert lifecycle(s,rows)=="REPLICATED"

def test_validation_requires_multiple_splits_symbols_regimes_and_samples():
    s=spec()
    rows=[ev("A","BTC","NORMAL","W1",80),
          ev("B","ETH","HIGH","W2",80),
          ev("C","BTC","HIGH","W3",80)]
    assert lifecycle(s,rows)=="VALIDATED"

def test_repeated_failures_are_remembered_as_rejection():
    s=spec()
    rows=[ev("A","BTC","NORMAL","W1",80,0,.4),
          ev("B","ETH","HIGH","W2",80,-1,.3),
          ev("C","BTC","HIGH","W3",80,0,.4)]
    assert lifecycle(s,rows)=="REJECTED"

def test_research_schema_contains_hypothesis_memory_and_durable_outcomes():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert '"scientific_hypothesis_memory"' in m
    assert '"durable_scientific_outcomes"' in m
    assert "UNIQUE(hypothesis_id,experiment_key)" in m
    assert "UNIQUE(event_id,hypothesis_fingerprint,horizon_ms)" in m


def test_pattern_mining_schema_tracks_multiple_testing():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert '"scientific_pattern_mining"' in m
    assert "scientific_mining_families" in m
    assert "corrected_p_value" in m


def test_regime_specific_pattern_can_validate_across_symbols_and_weeks():
    s=spec()
    rows=[ev("A","BTC","HIGH","W1",80),ev("B","ETH","HIGH","W2",80),ev("C","BTC","HIGH","W3",80)]
    assert lifecycle(s,rows)=="VALIDATED"


def test_simulation_promotion_schema_is_separate_from_hypothesis_status():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert '"scientific_simulation_promotion_gate"' in m
    assert "scientific_simulation_runs" in m
    assert "SIMULATION_PASSED" not in Path("grid/scientific_hypotheses.py").read_text(encoding="utf-8")


def test_simulation_trade_table_is_created_before_alter():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    create=m.index("CREATE TABLE IF NOT EXISTS scientific_simulation_trades")
    alter=m.index("ALTER TABLE scientific_simulation_trades")
    assert create<alter
