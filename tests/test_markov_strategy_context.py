from datetime import datetime,timedelta,timezone
from grid.conditional_markov import ConditionalMarkov
from grid.markov_strategy_context import enrich_simulated_trade,transition_edge
def test_simulated_trade_keeps_pretrade_markov_context_and_transition_edge():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[{"event_ts":t+timedelta(minutes=i),"symbol":"BTC","setup_type":"BREAKOUT",
           "market_state":("EXPANDING" if i%2==0 else "HIGH_VOL")} for i in range(60)]
    m=ConditionalMarkov(min_transitions=10).fit(rows)
    signal={"symbol":"BTC","setup_type":"BREAKOUT","market_state":"EXPANDING"}
    tr=enrich_simulated_trade(m,signal,{"pnl":2,"fees":.1,"slippage":.1,"state_to":"HIGH_VOL"})
    assert tr["state_from"]=="EXPANDING" and tr["markov_next"]
    e=transition_edge([tr])[0]
    assert e["expectancy"]>0 and e["state_to"]=="HIGH_VOL"
