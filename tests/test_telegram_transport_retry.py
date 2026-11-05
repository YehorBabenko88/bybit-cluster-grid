import pathlib

def test_telegram_long_poll_transport_failures_are_retryable():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "except (asyncio.TimeoutError,aiohttp.ClientError) as e:" in source
    assert '"event":"telegram_transport_retry"' in source
    assert "await asyncio.sleep(2)" in source

def test_telegram_application_failures_still_log_error():
    source=pathlib.Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'log.error("telegram loop failed",extra={"event":"telegram_error"' in source


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


def test_legacy_expansion_transport_failure_logs_class_without_url(monkeypatch,caplog):
    import asyncio
    from types import SimpleNamespace
    from grid import telegram_bot as bot
    monkeypatch.setattr(bot.settings,'telegram_allowed_chat_ids','-100')
    async def ready(*args): return [{'node_id':'PC1','expansion_notified_at':None}]
    async def send(*args): raise bot.aiohttp.ClientError('https://PRIVATE_TOKEN')
    async def mark(*args): raise AssertionError('failed message must not be marked delivered')
    monkeypatch.setattr(bot,'expansion_ready',ready)
    monkeypatch.setattr(bot,'tg_send',send)
    monkeypatch.setattr(bot,'mark_expansion_notified',mark)
    asyncio.run(bot._notify_expansion_ready(SimpleNamespace(pool=None),None))
    assert 'PRIVATE_TOKEN' not in caplog.text
    assert any(record.component=='ClientError' for record in caplog.records)
    assert 'log.exception' not in pathlib.Path('grid/telegram_bot.py').read_text(encoding='utf-8')
