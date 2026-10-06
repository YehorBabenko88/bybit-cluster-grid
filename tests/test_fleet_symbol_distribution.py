from grid.live_assignment_policy import guarded_live_symbols,pilot_universe
from grid.scheduler import weighted_assign,stabilize_assignments

UNIVERSE={s:{} for s in ("BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT")}

def test_pilot_policy_uses_scheduler_ownership_not_full_pilot_set():
    assigned=["BTCUSDT","SOLUSDT"]
    out=guarded_live_symbols(
        market_enabled=True,install_mode="PILOT",live_mode="PILOT_VALIDATING",
        node_assignments=assigned,instrument_symbols=UNIVERSE,
    )
    assert out==assigned
    assert "ETHUSDT" not in out

def test_two_pilot_nodes_partition_canary_universe_without_duplicates():
    nodes={"PC4":{"pressure_state":"NORMAL"},"PC5":{"pressure_state":"NORMAL"}}
    universe=pilot_universe(UNIVERSE)
    out=weighted_assign(universe,{"PC4":1.0,"PC5":1.0},nodes)
    flat=out["PC4"]+out["PC5"]
    assert sorted(flat)==sorted(universe)
    assert set(out["PC4"]).isdisjoint(out["PC5"])
    assert out["PC4"] and out["PC5"]

def test_full_universe_partition_has_exactly_one_owner():
    symbols=[f"S{i}USDT" for i in range(100)]
    nodes={f"PC{i}":{"pressure_state":"NORMAL"} for i in range(1,5)}
    out=weighted_assign(symbols,{n:1.0 for n in nodes},nodes)
    flat=[s for assigned in out.values() for s in assigned]
    assert len(flat)==len(symbols)
    assert len(set(flat))==len(symbols)
    assert all(out[n] for n in nodes)
    assert max(map(len,out.values()))-min(map(len,out.values())) <= 1

def test_offline_or_ineligible_previous_owner_is_forced_to_live_node():
    current={"OLD":["BTCUSDT"],"NEW":[]}
    proposed={"NEW":["BTCUSDT"]}
    live={"NEW":{"pressure_state":"NORMAL"}}
    out=stabilize_assignments(proposed,current,live,.10)
    assert out=={"NEW":["BTCUSDT"]}

def test_pressure_drained_symbol_moves_to_other_machine():
    nodes={
        "PC4":{"pressure_state":"REDUCE_LOAD","drained_symbols":["BTCUSDT"]},
        "PC5":{"pressure_state":"NORMAL"},
    }
    out=weighted_assign(["BTCUSDT"],{"PC4":10.0,"PC5":1.0},nodes)
    assert out["PC4"]==[]
    assert out["PC5"]==["BTCUSDT"]

def test_normal_policy_rejects_unassigned_symbols():
    out=guarded_live_symbols(
        market_enabled=True,install_mode="NORMAL",live_mode="NORMAL",
        node_assignments=["ETHUSDT"],instrument_symbols=UNIVERSE,
    )
    assert out==["ETHUSDT"]


def test_heterogeneous_capacity_gives_more_work_to_stronger_node():
    symbols=[f"H{i}USDT" for i in range(120)]
    nodes={"SMALL":{"pressure_state":"NORMAL"},"BIG":{"pressure_state":"NORMAL"}}
    out=weighted_assign(symbols,{"SMALL":1.0,"BIG":3.0},nodes)
    flat=out["SMALL"]+out["BIG"]
    assert len(flat)==len(symbols)
    assert len(set(flat))==len(symbols)
    assert len(out["BIG"]) > len(out["SMALL"])

def test_rebalance_stability_limits_healthy_churn():
    symbols=[f"C{i}USDT" for i in range(100)]
    nodes={"PC1":{"pressure_state":"NORMAL"},"PC2":{"pressure_state":"NORMAL"}}
    current={"PC1":symbols[:50],"PC2":symbols[50:]}
    # Deliberately request a complete swap. Stabilizer must cap healthy moves.
    proposed={"PC1":symbols[50:],"PC2":symbols[:50]}
    out=stabilize_assignments(proposed,current,nodes,.10)
    old_owner={s:n for n,ss in current.items() for s in ss}
    new_owner={s:n for n,ss in out.items() for s in ss}
    moved=sum(old_owner[s]!=new_owner[s] for s in symbols)
    assert moved <= 10
    assert len(set(s for ss in out.values() for s in ss))==100
