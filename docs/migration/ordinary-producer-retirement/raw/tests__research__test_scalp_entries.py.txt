from strattester.research.scalp_entries import *
from strattester.research.causal import CausalFeature
from strattester.research.volatility import VolatilitySnapshot,VolatilityRegime
from strattester.research.volume_profile import VolumeProfileSnapshot,POCMode
from strattester.strategies.builtin.research_scalp import scalp_hypotheses
from strattester.strategies.builtin.research_common import executable_hypotheses

def B(t,o,h,l,c,v=100):return {"t":t,"open":o,"high":h,"low":l,"close":c,"volume":v}
def V(t,known,vol=1.5,p=.7):
    return VolatilitySnapshot(t,known,.01,.01,.01,.02,vol,vol,p,VolatilityRegime.HIGH,"v")

def test_only_implemented_scalps_are_executable():
    names={x.name for x in executable_hypotheses(scalp_hypotheses())}
    assert names=={"SCALP_SWEEP_RECLAIM","SCALP_BREAKOUT_RETEST_VOLUME",
                   "SCALP_VOL_EXPANSION_CONTINUATION","SCALP_POC_RECLAIM"}

def test_sweep_entry_never_precedes_confirmed_event():
    bars=[B(60,99,101,98,100)]
    e=CausalFeature(60,120,"bullish_liquidity_sweep",{"level":99,"swing_time":0},"smc")
    x=sweep_reclaim_entries(bars,[e],bar_ms=60)
    assert x and x[0].decision_time>=120

def test_breakout_bar_is_not_reused_as_retest():
    bars=[B(60,99,102,99,101),B(120,101,102,99.9,101.2)]
    e=CausalFeature(60,120,"bullish_bos",{"level":100,"swing_time":0},"smc")
    xs=breakout_retest_volume_entries(bars,[e],[V(120,180)],bar_ms=60,min_volume_expansion=1.2)
    assert xs and xs[0].decision_time==180

def test_volatility_entry_waits_for_snapshot_known_at():
    b=B(60,100,104,99,103)
    xs=volatility_expansion_entries([b],[V(60,120)],bar_ms=60)
    assert xs and xs[0].decision_time==120

def test_poc_reclaim_uses_only_profile_known_by_decision():
    bars=[B(0,99,99.5,98.5,99),B(60,99,101,98.8,100.5)]
    p=VolumeProfileSnapshot(100,101,99,120,POCMode.TRADE_POC,2)
    xs=poc_reclaim_entries(bars,[p],bar_ms=60)
    assert xs and xs[0].decision_time==120
