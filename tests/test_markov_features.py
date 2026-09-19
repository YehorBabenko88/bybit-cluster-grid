from grid.markov_regime import MarkovRegimeModel,attach_markov_features
def test_markov_features_expose_regime_transition_probabilities():
    m=MarkovRegimeModel().fit(["QUIET","HIGH_VOL","IMPULSE","HIGH_VOL","QUIET"])
    x=attach_markov_features(m,[{"market_state":"HIGH_VOL"}])[0]
    assert 0<=x["markov_p_stay"]<=1
    assert 0<=x["markov_p_high_vol"]<=1
    assert abs(sum(x["markov_next_probabilities"].values())-1)<1e-9
