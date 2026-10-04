import asyncio
from grid import telegram_bot as tb


class DB:
    pool=object()


def test_research_cancel_requires_confirmation(monkeypatch):
    sent=[]
    async def send(session,chat_id,text,reply_markup=None):sent.append(text)
    monkeypatch.setattr(tb,"tg_send",send)
    tb._pending_confirms.clear()
    asyncio.run(tb.handle_command(DB(),object(),123,"/researchcancel abcdef12",{}))
    assert sent and "Confirm cancellation" in sent[-1]
    assert any(k[0]=="123" and v[0]=="research_cancel" and v[1]=="abcdef12"
               for k,v in tb._pending_confirms.items())
