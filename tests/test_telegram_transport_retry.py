import pathlib

def test_telegram_long_poll_transport_failures_are_retryable():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "except (asyncio.TimeoutError,aiohttp.ClientError) as e:" in source
    assert '"event":"telegram_transport_retry"' in source
    assert "await asyncio.sleep(2)" in source

def test_telegram_application_failures_still_log_error():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'log.exception("telegram loop failed",extra={"event":"telegram_error"})' in source


def test_telegram_failed_update_does_not_advance_cursor():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'if previous!="DONE":' in source
    assert 'raise RuntimeError("Telegram update not completed; cursor preserved")' in source
    assert '"event":"telegram_update_unresolved"' in source


def test_telegram_failed_command_is_quarantined_not_replayed():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'if previous=="FAILED":' in source
    assert '"event":"telegram_update_quarantined"' in source
    assert 'offset=await commit_telegram_cursor(db.pool,node_id,next_offset)' in source
    assert 'elif cmd=="/telegramfailed":' in source
    assert "WHERE status='FAILED'" in source


def test_telegram_stale_claim_is_quarantined_without_reexecution():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "status='CLAIMED'" in source
    assert "claimed_at<now()-interval '30 minutes'" in source
    assert "stale CLAIMED update; manual reconciliation required" in source
    assert 'if previous=="FAILED":' in source
