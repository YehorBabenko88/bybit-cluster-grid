from datetime import datetime,timezone
from grid.scientific_pattern_miner import (
    PatternObservation,generate_patterns,directional_stats,holm_adjust,strength_bucket)
from grid.scientific_mining_scheduler import previous_closed_iso_week
from grid.scientific_hypotheses import HypothesisSpec,Evidence,evidence_passes

def obs():
    return PatternObservation("BTC","2026-W40","HIGH","SURFACE_BREAK",1,
                              ("delta","oi","volume"),"S3",5.0)

def test_pattern_generation_is_bounded_and_requires_micro_agent():
    pats=generate_patterns(obs(),2,4,12)
    assert 0<len(pats)<=12
    assert all(any(t.startswith("agent=") for t in p) for p in pats)

def test_holm_adjustment_is_conservative():
    raw=[.001,.01,.04,.2]
    adj=holm_adjust(raw)
    assert all(a>=p for a,p in zip(adj,raw))
    assert adj[0]<=adj[1]<=adj[2]<=adj[3]

def test_directional_stats_handles_short_after_cost():
    st=directional_stats([-5,-4,-6,-5],-1,cost_bps=1)
    assert st["mean_net_bps"]>3
    assert st["hit_rate"]==1.0

def test_short_hypothesis_cost_is_applied_after_direction():
    s=HypothesisSpec("x","p",1000,-1,"v",{})
    e=Evidence("e","BTC","R","W",40,-3.0,.7,1.0,details={"corrected_p_value":.01})
    assert evidence_passes(s,e,min_edge_bps=.5)

def test_bad_corrected_p_value_blocks_mined_evidence():
    s=HypothesisSpec("x","p",1000,1,"v",{})
    e=Evidence("e","BTC","R","W",100,10,.8,1,details={"corrected_p_value":.2})
    assert not evidence_passes(s,e)

def test_scheduler_returns_previous_closed_iso_week():
    split,cutoff=previous_closed_iso_week(datetime(2026,10,6,12,tzinfo=timezone.utc))
    assert split=="2026-W40"
    assert cutoff==datetime(2026,10,5,0,tzinfo=timezone.utc)
