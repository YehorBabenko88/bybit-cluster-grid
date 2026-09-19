from datetime import datetime,timedelta,timezone
from grid.barrier_simulator import simulate_barrier
def test_same_bar_tp_sl_tie_is_conservatively_counted_as_stop():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    sig={"symbol":"BTC","setup_type":"BREAKOUT","event_ts":t,"direction":"LONG","entry_ref":100}
    bars=[{"ts":t,"open":100,"high":101,"low":99,"close":100.5}]
    r=simulate_barrier(sig,bars,tp_bps=50,sl_bps=50,horizon_bars=1,fee_bps=0,slippage_bps=0)
    assert r["exit_reason"]=="SL_SAME_BAR" and r["pnl"]<0
