import asyncio
from types import SimpleNamespace
from grid import telegram_bot as tb


class Pool:
    async def fetchrow(self,sql,*args):
        if "FROM research_runs" in sql and "FILTER" in sql:
            return {"active":2,"failed":1}
        if "FROM archive_compute_jobs" in sql:
            return {"active":3,"failed":1,"pending_materialize":1,
                    "queued":1,"running":2,"materialized":4}
        if "FROM ml_jobs" in sql:
            return {"active":4,"failed":1}
        if "FROM research_shards" in sql:
            return {"active":5,"failed":2}
        return None
    async def fetch(self,sql,*args):
        if "FROM research_runs" in sql:
            return [{"id":"run-1","kind":"strategy_backtest","status":"RUNNING",
                     "aggregate_fingerprint":None}]
        if "FROM ml_jobs" in sql:
            return [{"job_type":"strattester","status":"running","n":2}]
        if "FROM node_lifecycle" in sql:
            return [{"state":"ONLINE","n":2},{"state":"OFFLINE","n":1}]
        return []


class DB:
    pool=Pool()


def test_system_overview_includes_compute_research_archive(monkeypatch):
    async def fake_runtime(pool):
        return {"state":"ACTIVE","reason":None}
    monkeypatch.setattr(tb,"runtime_state",fake_runtime)
    nodes={"n1":{"last_seen":10**12},"n2":{"last_seen":10**12}}
    out=asyncio.run(tb.system_overview(DB(),nodes))
    assert out["runtime"]["state"]=="ACTIVE"
    assert out["research_active"]==2
    assert out["archive_active"]==3
    assert out["compute_active"]==4


def test_observability_commands_send_telegram_messages(monkeypatch):
    sent=[]
    async def fake_send(session,chat_id,text,reply_markup=None):
        sent.append(text)
    monkeypatch.setattr(tb,"tg_send",fake_send)
    async def run():
        for cmd in ("/research","/archive","/compute","/lifecycle"):
            await tb.handle_command(DB(),object(),123,cmd,{})
    asyncio.run(run())
    joined="\n".join(sent)
    assert "Research:" in joined
    assert "Archive compute:" in joined
    assert "Compute jobs:" in joined
    assert "Node lifecycle:" in joined
