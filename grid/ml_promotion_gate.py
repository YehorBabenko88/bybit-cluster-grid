from dataclasses import dataclass

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
    if int(metrics.get("samples",0))<policy.min_samples: reasons.append("insufficient_samples")
    if int(metrics.get("folds",0))<policy.min_folds: reasons.append("insufficient_temporal_folds")
    if int(metrics.get("profitable_folds",0))<policy.min_profitable_folds: reasons.append("unstable_across_folds")
    if float(metrics.get("max_drawdown_pct",999))>policy.max_drawdown_pct: reasons.append("drawdown")
    if float(metrics.get("fee_stress_factor",0))<policy.min_fee_stress_factor: reasons.append("fee_slippage_stress_missing")
    if int(metrics.get("symbol_count",0))<policy.min_symbol_count: reasons.append("narrow_symbol_coverage")
    if metrics.get("leakage_check_passed") is not True: reasons.append("leakage_check")
    return {"passed":not reasons,"reasons":reasons}
