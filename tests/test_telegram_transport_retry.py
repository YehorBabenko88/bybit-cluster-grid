import pathlib

def test_telegram_long_poll_transport_failures_are_retryable():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "except (asyncio.TimeoutError,aiohttp.ClientError) as e:" in source
    assert '"event":"telegram_transport_retry"' in source
    assert "await asyncio.sleep(2)" in source

def test_telegram_application_failures_still_log_error():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'log.exception("telegram loop failed",extra={"event":"telegram_error"})' in source
