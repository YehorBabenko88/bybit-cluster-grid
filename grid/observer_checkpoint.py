import json

class ObserverCheckpoint:
    def __init__(self,pool,name="historical_levels"):
        self.pool=pool; self.name=name

    async def load(self,symbol):
        r=await self.pool.fetchrow("""SELECT last_ts,state FROM observer_checkpoints
            WHERE observer=$1 AND symbol=$2""",self.name,symbol)
        return (r["last_ts"],dict(r["state"])) if r else (None,{})

    async def save(self,symbol,last_ts,state=None):
        await self.pool.execute("""INSERT INTO observer_checkpoints(observer,symbol,last_ts,state)
            VALUES($1,$2,$3,$4::jsonb)
            ON CONFLICT(observer,symbol) DO UPDATE SET last_ts=EXCLUDED.last_ts,
            state=EXCLUDED.state,updated_at=now()""",
            self.name,symbol,last_ts,json.dumps(state or {},default=str))
