from grid.command_receipts import CommandReceiptStore


def test_command_receipt_survives_restart_and_prevents_reexecution(tmp_path):
    path=tmp_path/"receipts.json"
    first=CommandReceiptStore(path,max_entries=100)
    assert first.get("cmd-1") is None
    first.put("cmd-1",True,{"state":"update_staged","version":"v2"},None)

    restarted=CommandReceiptStore(path,max_entries=100)
    row=restarted.get("cmd-1")
    assert row["ok"] is True
    assert row["result"]["version"]=="v2"


def test_command_receipts_are_bounded(tmp_path):
    path=tmp_path/"receipts.json"
    store=CommandReceiptStore(path,max_entries=100)
    for i in range(140):
        store.put(f"cmd-{i}",True,{"n":i},None)
    rows=store._load()
    assert len(rows)==100
    assert store.get("cmd-139") is not None
