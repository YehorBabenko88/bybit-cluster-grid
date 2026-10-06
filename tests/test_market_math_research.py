from grid.stochastic_research import poisson_event_diagnostics,markov_transition_matrix,spectral_band_power,quadratic_variation
from grid.timeseries_research import acf,difference,rolling_volatility,distributed_lag_correlations,volatility_regime,pair_error_correction

def test_poisson_diagnostics_regular_arrivals():
    d=poisson_event_diagnostics([i*1000 for i in range(100)])
    assert .99<d["rate_per_s"]<1.01 and d["cv_interarrival"]<1e-9

def test_markov_transition_matrix_is_normalized():
    m=markov_transition_matrix(["Q","Q","E","E","Q","E"])
    assert all(abs(sum(row.values())-1)<1e-9 for row in m.values())

def test_spectral_power_is_partitioned():
    p=spectral_band_power([(-1)**i for i in range(128)])
    assert p and .99<=sum(x["power_share"] for x in p)<=1.01

def test_quadratic_variation_positive():
    assert quadratic_variation([100,101,100,102])>0

def test_time_series_diagnostics():
    x=[float(i)+(.1 if i%2 else 0) for i in range(300)]
    assert len(acf(difference(x),5))==6
    assert len(rolling_volatility(difference(x),20))==len(x)-1
    assert distributed_lag_correlations(x,[0]+x[:-1],3)
    assert volatility_regime([.001,-.001]*100+ [.02,-.02]*10)["state"]=="HIGH"

def test_pair_error_correction_recovers_linear_relation():
    x=[float(i) for i in range(100)]
    y=[2*v+3+(.1 if i%2 else -.1) for i,v in enumerate(x)]
    r=pair_error_correction(x,y)
    assert r and abs(r["beta"]-2)<.01
