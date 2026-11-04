"""Ingress outcomes must gate effects and cursor advancement independently."""
import asyncio
from types import SimpleNamespace
import pytest
from grid import telegram_bot as bot
from grid.telegram_idempotency import Admission


def ingress(monkeypatch, decision, *, handler_fails=False, completion=True, backend=None, delivery=None, policy='{"/status":[42]}'):
    monkeypatch.setattr(bot.settings,'telegram_bot_token','synthetic')
    monkeypatch.setattr(bot.settings,'telegram_allowed_chat_ids','-100')
    monkeypatch.setenv('TELEGRAM_OPERATION_USER_IDS',policy)
    effects, completed, cursors, claims = [], [], [], []
    async def api(session, method, **kwargs):
        if method=='getMe': return {'result':{}}
        if claims: raise asyncio.CancelledError
        return {'result':[delivery or {'update_id':1,'message':{'chat':{'id':-100},'from':{'id':42,'is_bot':False},'text':'/status'}}]}
    async def admit(*args, **kwargs):
        claims.append((args,kwargs))
        if backend is not None: return await backend(*args,**kwargs)
        return Admission(decision,'receipt' if decision=='ACCEPTED' else None)
    async def handle(*args):
        effects.append(1)
        if handler_fails: raise ValueError('PRIVATE_TOKEN accidental exception')
    async def finish(*args, **kwargs):
        completed.append((args,kwargs))
        return completion
    async def cursor(*args): return 0
    async def commit(*args):
        cursors.append(args[-1])
        return args[-1]
    async def stop(*args): raise asyncio.CancelledError
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs): pass
    monkeypatch.setattr(bot.aiohttp,'ClientSession',lambda **kwargs: Session())
    for name,value in {'_tg_api':api,'admit_update':admit,'handle_command':handle,'finish_update':finish,
                       'telegram_cursor':cursor,'commit_telegram_cursor':commit}.items():
        monkeypatch.setattr(bot,name,value)
    monkeypatch.setattr(bot.asyncio,'sleep',stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.telegram_loop(SimpleNamespace(pool=None),{}))
    return effects,completed,cursors,claims


@pytest.mark.parametrize('decision',['DUPLICATE','REPLAY','DENIED','RATE_LIMITED'])
def test_nonaccepted_delivery_cannot_repeat_effects(monkeypatch,decision):
    effects,completed,cursors,claims=ingress(monkeypatch,decision)
    assert effects==completed==[]
    assert cursors==[2]
    assert claims[0][0][4]=='/status'
    assert claims[0][1]['authorized'] is True


@pytest.mark.parametrize('decision',['STUCK','CAPACITY'])
def test_unfinished_or_exhausted_delivery_holds_cursor(monkeypatch,decision):
    effects,completed,cursors,_=ingress(monkeypatch,decision)
    assert effects==completed==cursors==[]


def test_only_receipt_owned_completion_advances_cursor(monkeypatch):
    effects,completed,cursors,_=ingress(monkeypatch,'ACCEPTED')
    assert effects==[1] and cursors==[2]
    assert completed[0][0][1:]==(1,'receipt')


def test_rejected_completion_holds_cursor(monkeypatch):
    effects,completed,cursors,_=ingress(monkeypatch,'ACCEPTED',completion=False)
    assert effects==[1] and cursors==[]


def test_handler_failure_is_closed_audit_outcome_without_exception_text(monkeypatch,caplog):
    effects,completed,cursors,_=ingress(monkeypatch,'ACCEPTED',handler_fails=True)
    assert effects==[1] and cursors==[]
    assert completed[0][1]=={'failed':True}
    assert 'PRIVATE_TOKEN' not in caplog.text


@pytest.mark.parametrize('change',['revoked','actor','callback','callback_new_update'])
def test_real_admission_pending_claim_holds_async_poll_cursor(monkeypatch,change):
    from test_telegram_durable_admission import Store
    from grid import telegram_idempotency as durable
    store=Store()
    accepted=asyncio.run(durable.admit_update(store,1,-100,42,'/system','original',callback_id='original',authorized=True))
    assert accepted.decision=='ACCEPTED'
    delivery={'update_id':2 if change=='callback_new_update' else 1,'callback_query':{
        'id':'changed' if change=='callback' else 'original','data':'fleet:system',
        'from':{'id':43 if change in ('actor','callback_new_update') else 42,'is_bot':False},
        'message':{'chat':{'id':-100},'date':1}}}
    async def backend(pool,*args,**kwargs):
        return await durable.admit_update(store,*args,**kwargs)
    effects,completed,cursors,_=ingress(monkeypatch,None,backend=backend,delivery=delivery,
        policy='{}' if change=='revoked' else '{"/system":[42,43]}')
    assert effects==completed==cursors==[]
    assert store.audit[-1]['decision']=='STUCK'
    assert store.claims[1]['status']=='CLAIMED'
