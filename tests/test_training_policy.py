from grid.training_policy import (
    paper_eligible,historical_feature_allowed,merge_training_context,conflict_flags,training_source_policy)

def test_historical_l2_features_are_forbidden():
    assert historical_feature_allowed("volume_expansion")
    assert not historical_feature_allowed("book_velocity")
    assert not historical_feature_allowed("book_imbalance")

def test_live_observations_override_historical_priors_only_when_present():
    h={"volume_expansion":1.2,"book_velocity":None}
    l={"volume_expansion":2.0,"book_velocity":10}
    x=merge_training_context(h,l)
    assert x["volume_expansion"]==2.0 and x["book_velocity"]==10

def test_large_historical_live_disagreement_is_flagged():
    flags=conflict_flags({"volume_expansion":1.0},{"volume_expansion":3.0})
    assert flags and flags[0]["kind"]=="REGIME_SHIFT"

def test_paper_trading_requires_all_gates():
    assert paper_eligible(scientific_status="VALIDATED",simulation_status="SIMULATION_PASSED",phase="PAPER_TRADING")
    assert not paper_eligible(scientific_status="REPLICATED",simulation_status="SIMULATION_PASSED",phase="PAPER_TRADING")
    assert not paper_eligible(scientific_status="VALIDATED",simulation_status="WAITING_OOS",phase="PAPER_TRADING")
    assert not paper_eligible(scientific_status="VALIDATED",simulation_status="SIMULATION_PASSED",phase="LIVE_LEARNING")

def test_historical_source_cannot_validate_live_or_paper_trade():
    p=training_source_policy("HISTORICAL_STRATTESTER")
    assert p["may_seed_hypotheses"] and not p["may_validate_live"] and not p["may_paper_trade"]
