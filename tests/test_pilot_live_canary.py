from grid.pilot_live_canary import live_canary_health
def test_pilot_live_canary_requires_repeated_healthy_heartbeats():
    good={"integrity_ok":True,"pressure_state":"NORMAL","db_write_failures":0,"db_queue_ratio":.1,"active_symbols":5}
    assert not live_canary_health([good]*4)["healthy"]
    assert live_canary_health([good]*5)["healthy"]
    bad=dict(good);bad["db_write_failures"]=1
    assert not live_canary_health([good]*4+[bad])["healthy"]
