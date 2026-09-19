from grid.control_version_vector import compare_vectors,freshest_dominating

def r(a,b):return {"state":{"telegram_cursor":{"_version":a},"leader_epoch":{"_version":b}}}
def test_version_vector_selects_only_dominating_replica():
    assert compare_vectors({"a":2,"b":3},{"a":1,"b":3})==1
    assert freshest_dominating([r(1,1),r(2,1),r(2,3)])==r(2,3)
def test_concurrent_control_states_are_not_guessed():
    try:freshest_dominating([r(3,1),r(2,2)]);assert False
    except ValueError:pass
