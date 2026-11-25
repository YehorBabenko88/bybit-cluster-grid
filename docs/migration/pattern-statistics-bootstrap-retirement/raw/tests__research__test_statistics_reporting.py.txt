from types import SimpleNamespace
from strattester.research.statistics import evaluate_trades

def T(net,gross,fees,entry,exit,coverage='COMPLETE_HISTORY',vol='NORMAL',mae=0,mfe=0,r=0):
    return SimpleNamespace(net_pnl=net,gross_pnl=gross,fees=fees,entry_time=entry,exit_time=exit,
        metadata={'coverage':coverage,'volatility':vol,'mae':mae,'mfe':mfe,'r_multiple':r})

def test_statistics_compute_core_metrics_drawdown_and_streaks():
    xs=[T(2,2.2,.2,0,60,mae=-.5,mfe=3,r=1),T(-1,-.8,.2,60,180,mae=-2,mfe=.2,r=-.5),T(-2,-1.8,.2,180,240,mae=-3,mfe=.1,r=-1)]
    m=evaluate_trades(xs)
    assert m.trades==3 and m.wins==1 and m.losses==2
    assert round(m.win_rate,6)==round(1/3,6)
    assert m.net_pnl==-1 and round(m.fees,10)==.6
    assert m.expectancy==-1/3
    assert m.profit_factor==2/3
    assert m.max_drawdown==3
    assert m.max_consecutive_losses==2
    assert m.avg_holding_ms==80
    assert m.avg_mae<0 and m.avg_mfe>0

