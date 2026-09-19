from grid.cold_start import research_allowed,RESEARCH_READY,WARMING
def test_empty_or_warming_grid_cannot_start_research():
    assert not research_allowed({"state":WARMING,"ready":False})
    assert research_allowed({"state":RESEARCH_READY,"ready":True})
