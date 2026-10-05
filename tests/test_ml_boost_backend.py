from grid.ml_boost_backend import TabularBoostBackend
import pytest


def rows():
    return [
      {"features":{"a":1.0,"noise":"x"},"instrument_features":{"b":2},
       "target":{"ret":.1},"event_ts":i}
      for i in range(4)
    ]


def test_backend_requires_explicit_target():
    b=TabularBoostBackend("xgboost")
    with pytest.raises(ValueError,match="target_key"):
        b._xy(rows(),{})


def test_features_never_include_target():
    b=TabularBoostBackend("xgboost")
    X,y,names=b._xy(rows(),{"target_key":"ret"})
    assert names==["f.a","i.b"]
    assert y==[.1]*4
    assert all(len(x)==2 for x in X)


def test_non_numeric_target_fails_closed():
    r=rows();r[0]["target"]["ret"]="future"
    b=TabularBoostBackend("lightgbm")
    with pytest.raises(ValueError,match="non-numeric"):
        b._xy(r,{"target_key":"ret"})
