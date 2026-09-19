from datetime import datetime,timedelta,timezone
from grid.conditional_markov import ConditionalMarkov
def test_sparse_symbol_markov_falls_back_but_dense_symbol_uses_local_model():
    t=datetime(2026,1,1,tzinfo=timezone.utc);rows=[]
    for i in range(80):
        rows.append({"event_ts":t+timedelta(minutes=i),"symbol":"BTC","setup_type":"POC",
                     "market_state":"HIGH_VOL" if i%2 else "QUIET"})
    rows += [{"event_ts":t+timedelta(minutes=100+i),"symbol":"NEW","setup_type":"POC","market_state":s}
             for i,s in enumerate(["QUIET","HIGH_VOL","QUIET"])]
    m=ConditionalMarkov(min_transitions=20).fit(rows)
    _,btc=m.probabilities("BTC","POC","QUIET")
    _,new=m.probabilities("NEW","POC","QUIET")
    assert btc["scope"]==("BTC","POC")
    assert new["scope"]!=("NEW","POC")
