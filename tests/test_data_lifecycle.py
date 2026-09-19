from grid.data_lifecycle import useless_derived

def test_authoritative_decision_requires_derived_context():
    assert useless_derived("INSUFFICIENT",False,False)
    assert not useless_derived("INSUFFICIENT",False,True)
    assert not useless_derived("GOOD",True,False)
