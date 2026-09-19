import json
from grid import decommission as d

def test_coordinator_outage_alone_never_decommissions(tmp_path,monkeypatch):
    monkeypatch.setattr(d,"state_path",lambda:tmp_path/"state.json")
    now=1_000_000
    (tmp_path/"state.json").write_text(json.dumps({
      "last_coordinator_success":now-8*86400,
      "last_internet_success":now
    }))
    assert d.decommission_due(7,now) is False

def test_full_offline_over_threshold_decommissions(tmp_path,monkeypatch):
    monkeypatch.setattr(d,"state_path",lambda:tmp_path/"state.json")
    now=1_000_000
    (tmp_path/"state.json").write_text(json.dumps({
      "last_coordinator_success":now-8*86400,
      "last_internet_success":now-8*86400
    }))
    assert d.decommission_due(7,now) is True

def test_missing_state_is_safe(tmp_path,monkeypatch):
    monkeypatch.setattr(d,"state_path",lambda:tmp_path/"missing.json")
    assert d.decommission_due(7,1_000_000) is False
