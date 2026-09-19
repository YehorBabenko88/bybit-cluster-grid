from grid.ml_lifecycle import allowed,DATASET_TRANSITIONS,MODEL_TRANSITIONS
from grid.ml_promotion_gate import evaluate_gate

def test_lifecycle_cannot_skip_validation_stages():
    assert allowed(MODEL_TRANSITIONS,"CANDIDATE","OOS_PASSED")
    assert not allowed(MODEL_TRANSITIONS,"CANDIDATE","APPROVED")
    assert not allowed(MODEL_TRANSITIONS,"OOS_PASSED","SHADOW")
    assert allowed(DATASET_TRANSITIONS,"BUILDING","READY")

def test_gate_requires_robustness_not_just_profit():
    x=evaluate_gate({"samples":1000,"folds":5,"profitable_folds":5,"max_drawdown_pct":5,
      "fee_stress_factor":2,"symbol_count":10,"leakage_check_passed":False})
    assert not x["passed"] and "leakage_check" in x["reasons"]
    y=evaluate_gate({"samples":1000,"folds":5,"profitable_folds":4,"max_drawdown_pct":10,
      "fee_stress_factor":2,"symbol_count":10,"leakage_check_passed":True})
    assert y["passed"]
