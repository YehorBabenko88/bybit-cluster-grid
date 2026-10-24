import json
from grid.snapshot_export_cli import main, plan, verify_receipt_structure


def test_plan_blocks_unattested_history():
    result = plan()
    assert result["status"] == "BLOCKED"
    assert not result["writes_permitted"]
    assert "historical_first_availability_not_attested" in result["blockers"]


def test_verify_never_authenticates_unsigned_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({"producer_id": "fake", "signature": "fake"}))
    assert verify_receipt_structure(path)["status"] == "BLOCKED"


def test_disposable_mode_does_not_write(tmp_path, capsys):
    target = tmp_path / "new"
    assert main(["--export-disposable", str(target)]) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_plan_exit_is_blocked(capsys):
    assert main(["--plan"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_duplicate_json_keys_fail_closed(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"source_id":"a","source_id":"b"}')
    result = verify_receipt_structure(path)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "invalid_receipt"


def test_oversized_receipt_fail_closed(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * 65537)
    assert verify_receipt_structure(path)["status"] == "BLOCKED"


def test_symlink_receipt_fail_closed(tmp_path):
    import pytest
    original = tmp_path / "receipt.json"
    original.write_text("{}")
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    assert verify_receipt_structure(link)["status"] == "BLOCKED"
