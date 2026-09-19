from grid.rollout import build_waves

def flatten(waves):
    return [n for w in waves for n in w]

def test_canary_excluded_and_nodes_unique():
    nodes=["pc1","pc2","pc3","pc4","pc5","pc6","pc7","pc8"]
    waves=build_waves(nodes,"pc1")
    flat=flatten(waves)
    assert "pc1" not in flat
    assert len(flat)==len(set(flat))==7
    assert set(flat)==set(nodes)-{"pc1"}

def test_two_nodes():
    assert build_waves(["pc1","pc2"],"pc1")==[["pc2"]]

def test_five_nodes_cover_all():
    waves=build_waves(["pc1","pc2","pc3","pc4","pc5"],"pc1")
    assert flatten(waves)==["pc2","pc3","pc4","pc5"]
    assert all(waves)

def test_single_canary_has_no_stable_waves():
    assert build_waves(["pc1"],"pc1")==[]

def test_order_is_deterministic():
    a=build_waves(["pc5","pc1","pc3","pc2","pc4"],"pc1")
    b=build_waves(["pc2","pc4","pc5","pc3","pc1"],"pc1")
    assert a==b
