from strattester.research.validation import chronological_split,walk_forward_folds,freeze_parameters
from strattester.research.resampling import bootstrap_expectancy,monte_carlo_max_drawdowns

def test_chronological_split_never_overlaps_or_uses_future():
    rows=list(range(10))
    s=chronological_split(rows,train_size=6,validation_size=2,test_size=2)
    assert s.train==(0,1,2,3,4,5)
    assert s.validation==(6,7)
    assert s.test==(8,9)
    assert max(s.train)<min(s.validation)<min(s.test)

def test_walk_forward_folds_are_chronological():
    fs=walk_forward_folds(list(range(12)),train_size=4,validation_size=2,test_size=2,step=2)
    assert len(fs)>=2
    for f in fs:
        assert max(f.train)<min(f.validation)<min(f.test)

def test_selected_parameters_are_frozen_before_test():
    p=freeze_parameters({'threshold':.7},selected_through=7)
    assert p.values=={'threshold':.7}
    assert p.selected_through==7

def test_bootstrap_expectancy_is_seeded_and_contains_sample_mean():
    xs=[1.0,-1.0,2.0,0.5]
    a=bootstrap_expectancy(xs,iterations=200,seed=7)
    b=bootstrap_expectancy(xs,iterations=200,seed=7)
    assert a==b
    assert a.lower<=sum(xs)/len(xs)<=a.upper

def test_monte_carlo_drawdown_is_seeded():
    xs=[2,-1,-2,3,-.5]
    a=monte_carlo_max_drawdowns(xs,iterations=100,seed=9)
    b=monte_carlo_max_drawdowns(xs,iterations=100,seed=9)
    assert a==b and len(a)==100 and min(a)>=0
