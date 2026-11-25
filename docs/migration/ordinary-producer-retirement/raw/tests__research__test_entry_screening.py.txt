from strattester.strategies.builtin.research_scalp import scalp_hypotheses
from strattester.strategies.builtin.research_common import executable_hypotheses

def test_spec_only_hypotheses_cannot_enter_executable_ranking():
    hs=scalp_hypotheses()
    executable=executable_hypotheses(hs)
    assert executable
    assert all(x.execution_status=="EXECUTABLE" and x.signal_generator for x in executable)
    assert all(x not in executable for x in hs if x.execution_status=="SPEC_ONLY")
