from pathlib import Path


def test_worker_rejects_missing_command_ids_before_execution():
    source=Path("grid/worker.py").read_text(encoding="utf-8")
    start=source.index('for cmd in reply.get("commands",[]):')
    reject=source.index('if not isinstance(cmd,dict) or not isinstance(cmd.get("id"),str) or not cmd["id"].strip():',start)
    execute=source.index('result=await execute_command(self,cmd)',start)
    assert start < reject < execute
    assert 'extra={"event":"invalid_control_command_id"}' in source[reject:execute]
    assert "continue" in source[reject:execute]
