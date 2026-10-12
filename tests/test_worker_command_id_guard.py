from pathlib import Path


def test_worker_rejects_missing_command_ids_before_execution():
    source=Path("grid/worker.py").read_text(encoding="utf-8")
    start=source.index('for cmd in reply.get("commands",[]):')
    reject=source.index('if not isinstance(cmd,dict) or not isinstance(cmd.get("id"),str) or not _valid_control_command_id(cmd["id"]):',start)
    execute=source.index('result=await execute_command(self,cmd)',start)
    assert start < reject < execute
    assert 'extra={"event":"invalid_control_command_id"}' in source[reject:execute]
    assert "continue" in source[reject:execute]


def test_control_command_ids_must_be_canonical_uuid():
    from grid.worker import _valid_control_command_id
    assert _valid_control_command_id("123e4567-e89b-12d3-a456-426614174000")
    for value in ("", " ", "not-a-uuid", "../commands", "123e4567-e89b-12d3-a456-426614174000/extra",
                  "123E4567-E89B-12D3-A456-426614174000", None, 123):
        assert not _valid_control_command_id(value)
