import json
from grid import telegram_bot as bot


def test_chat_allowlist_does_not_authorize_a_user(monkeypatch):
    monkeypatch.setattr(bot.settings, 'telegram_allowed_chat_ids', '-100')
    monkeypatch.delenv('TELEGRAM_OPERATION_USER_IDS', raising=False)
    assert not bot.allowed(-100, 42, '/status')


def test_per_operation_grant_is_exact_and_fail_closed(monkeypatch):
    monkeypatch.setattr(bot.settings, 'telegram_allowed_chat_ids', '-100')
    monkeypatch.setenv('TELEGRAM_OPERATION_USER_IDS', json.dumps({'/status': [42]}))
    assert bot.allowed(-100, 42, '/status')
    assert not bot.allowed(-100, 43, '/status')
    assert not bot.allowed(-100, 42, '/stop')
    assert not bot.allowed(-101, 42, '/status')
    assert not bot.allowed(-100, None, '/status')


def test_malformed_or_wildcard_policy_never_grants_access(monkeypatch):
    monkeypatch.setattr(bot.settings, 'telegram_allowed_chat_ids', '-100')
    for policy in ('broken', '[]', '{"*": [42]}', '{"/status": "42"}', '{"/status": [true]}'):
        monkeypatch.setenv('TELEGRAM_OPERATION_USER_IDS', policy)
        assert not bot.allowed(-100, 42, '/status')


def test_handler_rejects_mutations_before_accessing_database(monkeypatch):
    import asyncio
    sent = []
    async def send(session, chat, text, *args):
        sent.append(text)
    monkeypatch.setattr(bot, 'tg_send', send)
    for command in ('/stop worker', '/controlupdate v1', '/confirm CODE', '/cleanup', '/deletestatus abc', '/unknown'):
        asyncio.run(bot.handle_command(None, None, -100, command, {}))
    assert len(sent) == 6
    assert all('NOT_IMPLEMENTED' in text for text in sent)


def test_polling_has_no_implicit_fleet_mutation_calls():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(bot.telegram_loop))
    names = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not names & {'reconcile_fleet_operation', '_maybe_finalize_fleet_delete', '_notify_expansion_ready'}


def test_ingress_uses_callback_sender_and_denies_missing_or_bot_identity(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    monkeypatch.setattr(bot.settings, 'telegram_bot_token', 'synthetic')
    monkeypatch.setattr(bot.settings, 'telegram_allowed_chat_ids', '-100')
    monkeypatch.setenv('TELEGRAM_OPERATION_USER_IDS', '{"/system": [42]}')
    received = []
    async def handle(*args):
        received.append(args[3])
    async def cursor(*args): return 0
    async def commit(*args): return args[-1]
    async def claim(*args): return True
    async def complete(*args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return None
    monkeypatch.setattr(bot.aiohttp, 'ClientSession', lambda **kwargs: Session())
    monkeypatch.setattr(bot, 'handle_command', handle)
    monkeypatch.setattr(bot, 'telegram_cursor', cursor)
    monkeypatch.setattr(bot, 'commit_telegram_cursor', commit)
    monkeypatch.setattr(bot, 'claim_update', claim)
    monkeypatch.setattr(bot, 'complete_update', complete)
    for sender in (None, {'id': 43, 'is_bot': False}, {'id': 42, 'is_bot': True}, {'id': 42, 'is_bot': False}):
        calls = 0
        async def api(session, method, **kwargs):
            nonlocal calls
            if method == 'getMe': return {'result': {}}
            calls += 1
            if calls > 1: raise asyncio.CancelledError
            return {'result': [{'update_id': 1, 'callback_query': {
                'id': 'synthetic', 'data': 'fleet:system', 'from': sender,
                'message': {'chat': {'id': -100}, 'from': {'id': 42, 'is_bot': False}},
            }}]}
        monkeypatch.setattr(bot, '_tg_api', api)
        try:
            asyncio.run(bot.telegram_loop(SimpleNamespace(pool=None), {}))
        except asyncio.CancelledError:
            pass
    assert received == ['/system']
