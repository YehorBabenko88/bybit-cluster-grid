from strattester.research.execution import Signal,ExecutionPolicy,simulate_trade

def test_limit_entry_cannot_get_free_same_bar_survival():
    bars=[
      {"t":60_000,"open":101.0,"high":102.0,"low":98.0,"close":101.0},
      {"t":120_000,"open":101.0,"high":103.0,"low":100.0,"close":102.0},
    ]
    sig=Signal(decision_time=0,side="long",entry_kind="limit",entry_price=100.0,
               stop_loss=99.0,take_profit=102.0)
    t=simulate_trade(sig,bars,ExecutionPolicy(bar_ms=60_000,fee_rate=0,slippage_bps=0))
    assert t.entry_time==60_000
    assert t.exit_time==60_000
    assert t.exit_reason=="SL"

def test_market_entry_checks_same_bar_stop():
    bars=[{"t":60_000,"open":100.0,"high":101.0,"low":98.0,"close":100.0}]
    sig=Signal(decision_time=60_000,side="long",entry_kind="market",entry_price=None,
               stop_loss=99.0,take_profit=102.0)
    t=simulate_trade(sig,bars,ExecutionPolicy(bar_ms=60_000,fee_rate=0,slippage_bps=0))
    assert t.exit_reason=="SL"
