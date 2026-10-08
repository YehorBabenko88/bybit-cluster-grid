import math

import pytest

from grid.data_quality import safe_float


@pytest.mark.parametrize("value",["NaN","Infinity","-Infinity",float("nan"),float("inf"),float("-inf"),"1e10000"])
def test_nonfinite_values_are_rejected(value):
    assert safe_float(value) is None
    assert safe_float(value,default=-1)==-1


@pytest.mark.parametrize("value,expected",[("1.25",1.25),(2,2.0),("-0.5",-0.5)])
def test_finite_values_remain_valid(value,expected):
    assert safe_float(value)==expected


def test_overflow_and_invalid_values_use_default():
    assert safe_float(10**10000,default=0)==0
    assert safe_float("not-a-number",default=0)==0
