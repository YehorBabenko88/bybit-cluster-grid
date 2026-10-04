import json
from grid import command_receipts as cr


def test_command_receipt_roundtrip_and_replay(tmp_path,monkeypatch):
    p=tmp_path/"receipts.json"
    monkeypatch.setattr(cr,"_path",lambda:p)
    assert cr.get("cmd-1") is None
    cr.put("cmd-1",True,{"state":"stopped"},None)
    first=cr.get("cmd-1")
    assert first["ok"] is True
    assert first["result"]=={"state":"stopped"}
    # A retry reads the prior outcome instead of executing the action again.
    assert cr.get("cmd-1")==first


def test_command_receipts_are_bounded(tmp_path,monkeypatch):
    p=tmp_path/"receipts.json"
    monkeypatch.setattr(cr,"_path",lambda:p)
    monkeypatch.setattr(cr,"MAX_ENTRIES",3)
    for i in range(6):
        cr.put(f"c-{i}",True,{"i":i})
    data=json.loads(p.read_text())
    assert len(data)==3
