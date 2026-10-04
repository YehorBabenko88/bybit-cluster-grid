import asyncio
from grid import telegram_bot as tb


class DB:
    pool=object()


def test_stop_requires_confirmation_before_enqueue(monkeypatch):
    sent=[];queued=[]
    async def send(session,chat_id,text,reply_markup=None):sent.append(text)
    async def enqueue(pool,node,action,payload):queued.append((node,action));return "id"
    monkeypatch.setattr(tb,"tg_send",send)
    monkeypatch.setattr(tb,"enqueue_command",enqueue)
    tb._pending_confirms.clear()
    nodes={"n1":{"last_seen":10**12}}
    asyncio.run(tb.handle_command(DB(),object(),123,"/stop n1",nodes))
    assert queued==[]
    assert "Confirm stop" in sent[-1]
    assert any(v[0]=="node_command" and v[1]["action"]=="stop"
               for v in tb._pending_confirms.values())


def test_unknown_node_is_not_queued(monkeypatch):
    sent=[];queued=[]
    async def send(session,chat_id,text,reply_markup=None):sent.append(text)
    async def enqueue(pool,node,action,payload):queued.append((node,action));return "id"
    monkeypatch.setattr(tb,"tg_send",send);monkeypatch.setattr(tb,"enqueue_command",enqueue)
    asyncio.run(tb.handle_command(DB(),object(),123,"/pause missing",{}))
    assert queued==[]
    assert "Unknown node" in sent[-1]
