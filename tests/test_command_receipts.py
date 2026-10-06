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


def test_restart_commands_request_graceful_worker_shutdown():
    import asyncio
    from grid.agent_commands import execute_command

    class Worker:
        restart_requested=False

    async def run():
        worker=Worker()
        result=await execute_command(worker,{"action":"restart","payload":{}})
        assert result["state"]=="restarting"
        assert worker.restart_requested is True

    asyncio.run(run())


def test_lifecycle_commands_do_not_hard_exit_worker_process():
    from pathlib import Path
    source=Path("grid/agent_commands.py").read_text(encoding="utf-8")
    assert "os._exit(75)" not in source
    assert "restart_requested=True" in source
