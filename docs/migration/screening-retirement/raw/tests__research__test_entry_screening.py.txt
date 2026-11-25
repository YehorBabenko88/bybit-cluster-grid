from strattester.research.entry_screening import screen_entry_pattern
from strattester.strategies.builtin.research_scalp import scalp_hypotheses
from strattester.strategies.builtin.research_common import executable_hypotheses

def test_majority_losing_oos_pattern_is_rejected():
    folds=[
      {"trades":30,"expectancy":-0.4,"profit_factor":.8},
      {"trades":30,"expectancy":-0.2,"profit_factor":.9},
      {"trades":30,"expectancy":.1,"profit_factor":1.1},
    ]
    v=screen_entry_pattern("x",folds)
    assert v.status=="REJECT"
    assert "MAJORITY_LOSS_MAKING" in v.reasons

def test_stable_oos_pattern_can_survive():
    folds=[
      {"trades":30,"expectancy":.4,"profit_factor":1.2},
      {"trades":30,"expectancy":.2,"profit_factor":1.1},
      {"trades":30,"expectancy":.3,"profit_factor":1.15},
    ]
    assert screen_entry_pattern("x",folds).status=="KEEP"

def test_spec_only_hypotheses_cannot_enter_executable_ranking():
    hs=scalp_hypotheses()
    executable=executable_hypotheses(hs)
    assert executable
    assert all(x.execution_status=="EXECUTABLE" and x.signal_generator for x in executable)
    assert all(x not in executable for x in hs if x.execution_status=="SPEC_ONLY")
