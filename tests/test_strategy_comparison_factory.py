import asyncio
from grid.strategy_comparison_factory import comparison_key,VARIANTS
def test_comparison_key_is_stable_and_variant_specific():
    a=comparison_key("d1","POC","BASE",{"fees":1})
    b=comparison_key("d1","POC","BASE",{"fees":1})
    c=comparison_key("d1","POC","MARKOV",{"fees":1})
    assert a==b and a!=c
    assert set(VARIANTS)=={"BASE","REGIME","MARKOV","REGIME_MARKOV","ML","ML_MARKOV"}
