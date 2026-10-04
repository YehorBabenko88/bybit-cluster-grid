from grid.ml_dispatcher import compatible_nodes


def test_strattester_jobs_require_capability_and_exact_version():
    nodes={
        "a":{"compute_capabilities":{"strattester":True},"strattester_version":"abc"},
        "b":{"compute_capabilities":{"strattester":True},"strattester_version":"def"},
        "c":{"compute_capabilities":{},"strattester_version":"abc"},
    }
    assert set(compatible_nodes(nodes,"strattester",{"strattester_version":"abc"}))=={"a"}
    assert set(compatible_nodes(nodes,"strattester",{"strattester_version":"def"}))=={"b"}
    assert set(compatible_nodes(nodes,"strattester",{}))=={"a","b"}


def test_non_strattester_jobs_are_not_filtered():
    nodes={"a":{},"b":{}}
    assert compatible_nodes(nodes,"train",{}) is nodes
