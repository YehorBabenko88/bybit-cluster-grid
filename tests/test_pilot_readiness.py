from grid.pilot_readiness import readiness
def test_expansion_blocked_until_every_pilot_gate_passes():
    x={k:True for k in ("history_repaired","levels_complete","research_complete","import_verified")}
    r=readiness(x)
    assert not r["ready"] and r["missing"]==["live_canary_healthy"]
    x["live_canary_healthy"]=True
    assert readiness(x)["ready"]
