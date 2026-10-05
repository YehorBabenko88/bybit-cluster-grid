import asyncio
from grid.strategy_comparison_factory import comparison_key,VARIANTS
def test_comparison_key_is_stable_and_variant_specific():
    a=comparison_key("d1","POC","BASE",{"fees":1})
    b=comparison_key("d1","POC","BASE",{"fees":1})
    c=comparison_key("d1","POC","MARKOV",{"fees":1})
    assert a==b and a!=c
    assert set(VARIANTS)=={"BASE","REGIME","MARKOV","REGIME_MARKOV","ML","ML_MARKOV"}


def test_strategy_executor_uses_shared_process_supervisor():
    from pathlib import Path
    src=Path("grid/strategy_executor.py").read_text(encoding="utf-8")
    assert "run_supervised_process" in src
    assert "ram_limit_mb=ram_limit_mb" in src
    assert "asyncio.create_subprocess_exec" not in src
