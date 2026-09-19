from datetime import datetime,timedelta,timezone
from grid.historical_variant_engine import chronological_folds,select_validation
def test_variant_engine_trains_markov_only_on_prior_rows_and_flags_missing_ml():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[{"event_ts":t+timedelta(minutes=i),"symbol":"BTC","setup_type":"BREAKOUT",
           "market_state":"EXPANDING" if i%2==0 else "HIGH_VOL","regime":"EXPANDING" if i%2==0 else "HIGH_VOL"} for i in range(140)]
    fold,train,val=chronological_folds(rows,min_train=100,folds=2)[0]
    picked,meta=select_validation("BASE","BREAKOUT",train,val,min_transitions=10)
    assert len(picked)==len(val)
    picked,meta=select_validation("ML","BREAKOUT",train,val,min_transitions=10)
    assert not picked and meta["missing_ml_score"]
