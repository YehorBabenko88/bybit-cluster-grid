from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class GatePolicy:
    min_samples:int=500
    min_folds:int=4
    min_profitable_folds:int=3
    max_drawdown_pct:float=25.0
    min_fee_stress_factor:float=1.5
    min_symbol_count:int=3

def evaluate_gate(metrics,policy=GatePolicy()):
    reasons=[]
    def number(key,default):
        try:
            value=float(metrics.get(key,default))
            return value if isfinite(value) else default
        except (TypeError,ValueError,OverflowError):
            return default
    if number("samples",0)<policy.min_samples: reasons.append("insufficient_samples")
    if number("folds",0)<policy.min_folds: reasons.append("insufficient_temporal_folds")
    if number("profitable_folds",0)<policy.min_profitable_folds: reasons.append("unstable_across_folds")
    if number("max_drawdown_pct",float("inf"))>policy.max_drawdown_pct: reasons.append("drawdown")
    if number("fee_stress_factor",0)<policy.min_fee_stress_factor: reasons.append("fee_slippage_stress_missing")
    if number("symbol_count",0)<policy.min_symbol_count: reasons.append("narrow_symbol_coverage")
    if metrics.get("leakage_check_passed") is not True: reasons.append("leakage_check")
    return {"passed":not reasons,"reasons":reasons}
