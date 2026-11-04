import pathlib

def test_telegram_long_poll_transport_failures_are_retryable():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "except (asyncio.TimeoutError,aiohttp.ClientError) as e:" in source
    assert '"event":"telegram_transport_retry"' in source
    assert "await asyncio.sleep(2)" in source

def test_telegram_application_failures_still_log_error():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'log.error("telegram loop failed",extra={"event":"telegram_error"})' in source


def test_auth_transport_failure_does_not_log_private_exception_text(monkeypatch,caplog):
    import asyncio
    from types import SimpleNamespace
    from grid import telegram_bot as bot
    monkeypatch.setattr(bot.settings,'telegram_bot_token','synthetic')
    monkeypatch.setattr(bot.settings,'telegram_allowed_chat_ids','-100')
    async def cursor(*args): return 0
    async def api(*args,**kwargs): raise bot.aiohttp.ClientError('PRIVATE_TOKEN in request URL')
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    monkeypatch.setattr(bot.aiohttp,'ClientSession',lambda **kwargs: Session())
    monkeypatch.setattr(bot,'telegram_cursor',cursor)
    monkeypatch.setattr(bot,'_tg_api',api)
    asyncio.run(bot.telegram_loop(SimpleNamespace(pool=None),{}))
    assert 'PRIVATE_TOKEN' not in caplog.text
    assert 'bot authentication failed' in caplog.text
