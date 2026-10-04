import asyncio
import pytest
from grid.telegram_bot import tg_send


class Response:
    def __init__(self,status,payload):
        self.status=status;self.payload=payload
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def json(self,content_type=None):return self.payload


class Session:
    def __init__(self,response):self.response=response;self.calls=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs));return self.response


def test_tg_send_requires_telegram_ok(monkeypatch):
    async def run():
        s=Session(Response(200,{"ok":False,"description":"bad"}))
        with pytest.raises(RuntimeError,match="Telegram send failed"):
            await tg_send(s,123,"hello")
    asyncio.run(run())


def test_tg_send_clips_message_and_uses_timeout(monkeypatch):
    async def run():
        s=Session(Response(200,{"ok":True}))
        await tg_send(s,123,"x"*5000)
        _,kwargs=s.calls[0]
        assert len(kwargs["json"]["text"])==4000
        assert kwargs["timeout"]==15
    asyncio.run(run())
