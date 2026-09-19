from grid.event_conditioned_markov import EventConditionedMarkov
def test_event_conditioned_markov_uses_fixed_horizon_outcomes_by_setup():
    rows=[]
    for _ in range(40):
        rows.append({"symbol":"BTC","setup_type":"BREAKOUT","market_state":"EXPANDING","state_to":"IMPULSE"})
        rows.append({"symbol":"BTC","setup_type":"POC","market_state":"HIGH_VOL","state_to":"DECAY"})
    m=EventConditionedMarkov(min_transitions=20).fit(rows)
    p,b=m.probabilities("BTC","BREAKOUT","EXPANDING")
    assert p["IMPULSE"]>p["DECAY"] and b["scope"][:2]==("BTC","BREAKOUT")
    p,_=m.probabilities("BTC","POC","HIGH_VOL")
    assert p["DECAY"]>p["IMPULSE"]
