from pathlib import Path

def test_command_ack_checks_http_status_and_preserves_receipt_first():
    source=Path("grid/worker.py").read_text(encoding="utf-8")
    ack=source.index('settings.coordinator_url+f"/commands/{cmd[\'id\']}/result"')
    receipt=source.index('self.command_receipts.put(cmd.get("id"),ok,result,error)')
    status=source.index("ack_response.raise_for_status()",ack)
    assert receipt < ack < status
    assert "async with s.post(" in source[:ack]
    assert 'log.exception("command acknowledgement failed"' in source[status:]
