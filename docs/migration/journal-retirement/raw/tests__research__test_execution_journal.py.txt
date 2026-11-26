from strattester.research.execution import ExecutionPolicy,Signal,simulate_trade
from strattester.research.journal import TradeJournal

def _bar(t,o,h,l,c):
    return {'t':t,'open':o,'high':h,'low':l,'close':c}

def test_market_signal_checks_stop_on_entry_bar():
    bars=[_bar(0,100,101,99,100),_bar(60,100,103,99,102),_bar(120,102,104,101,103)]
    s=Signal(decision_time=60,side='long',entry_kind='market',entry_price=None,stop_loss=99,take_profit=103)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert t.entry_time==60 and t.entry_price==100
    assert t.exit_time==60 and t.exit_price==99 and t.exit_reason=='SL'

def test_ambiguous_bar_uses_conservative_stop_first():
    bars=[_bar(0,100,101,99,100),_bar(60,100,101,99,100),_bar(120,100,106,94,100)]
    s=Signal(decision_time=60,side='long',entry_kind='market',entry_price=None,stop_loss=95,take_profit=105)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0,ambiguous_policy='SL_FIRST'))
    assert t.exit_reason=='SL' and t.exit_price==95

def test_gap_and_costs_are_applied():
    bars=[_bar(0,100,101,99,100),_bar(60,100,101,99,100),_bar(120,90,92,89,91)]
    s=Signal(decision_time=60,side='long',entry_kind='market',entry_price=None,stop_loss=95,take_profit=105)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=.001,slippage_bps=10))
    assert t.exit_reason=='SL_GAP'
    assert t.net_pnl < t.gross_pnl

def test_limit_order_is_not_eligible_before_next_bar():
    bars=[_bar(0,100,101,98,100),_bar(60,100,101,98,100),_bar(120,100,102,99,101),_bar(180,101,103,100,102)]
    s=Signal(decision_time=60,side='long',entry_kind='limit',entry_price=99.5,stop_loss=98,take_profit=103)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert t.entry_time==120

def test_journal_preserves_research_metadata():
    bars=[_bar(0,100,101,99,100),_bar(60,100,101,99,100),_bar(120,100,103,99,102)]
    s=Signal(decision_time=60,side='long',entry_kind='market',entry_price=None,stop_loss=98,take_profit=103)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0),metadata={'coverage':'COMPLETE_HISTORY','volatility':'HIGH','poc_mode':'TRADE_POC'})
    j=TradeJournal(); j.append(t)
    row=j.rows[0]
    assert row.metadata['coverage']=='COMPLETE_HISTORY'
    assert row.metadata['volatility']=='HIGH'
    assert row.metadata['poc_mode']=='TRADE_POC'


def test_long_limit_gapped_below_fills_at_better_open():
    bars=[_bar(0,100,101,99,100),_bar(60,98,100,97,99),_bar(120,99,102,98,101)]
    s=Signal(decision_time=0,side='long',entry_kind='limit',entry_price=99.5,stop_loss=95,take_profit=102)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert t.entry_time==60 and t.entry_price==98

def test_short_limit_gapped_above_fills_at_better_open():
    bars=[_bar(0,100,101,99,100),_bar(60,102,103,100,101),_bar(120,101,102,98,99)]
    s=Signal(decision_time=0,side='short',entry_kind='limit',entry_price=100.5,stop_loss=105,take_profit=98)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert t.entry_time==60 and t.entry_price==102


def test_take_profit_gap_is_filled_at_target_not_optimistic_open():
    bars=[_bar(0,100,101,99,100),_bar(60,100,101,99,100),_bar(120,110,111,109,110)]
    s=Signal(decision_time=60,side='long',entry_kind='market',entry_price=None,stop_loss=95,take_profit=105)
    t=simulate_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert t.exit_reason=='TP_GAP'
    assert t.exit_price==105
