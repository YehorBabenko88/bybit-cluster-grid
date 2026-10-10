"""Background CONTROL consumer for the scientific research layer."""
from __future__ import annotations
import asyncio,datetime,json,logging,time
from .scientific_orchestrator import ScientificResearchOrchestrator
from .scientific_event_router import route_market_event
from .retention_v2 import register_consumer
from .control_state import set_consumer_watermarks
from .micro_agents import MicroSignal
from .scientific_mining_scheduler import ScientificMiningScheduler
from .scientific_simulation_gate import ScientificSimulationGate
from .scientific_method_registry import ScientificMethodRegistry,ScientificMethod
from .book_tape_research import VERSION as BOOK_TAPE_VERSION
from .book_tape_paper import BookTapePaperLearner

log=logging.getLogger("scientific_service")

class ScientificResearchService:
    def __init__(self,pool,poll_seconds=.25,batch_size=500):
        self.pool=pool;self.poll_seconds=float(poll_seconds);self.batch_size=max(10,int(batch_size))
        self.orchestrator=ScientificResearchOrchestrator()
        self.stop_event=asyncio.Event();self.last_id=0;self.processed=0;self.scheduled=0
        self.errors=0;self.last_event_ts=None;self.started=False
        self.mining=ScientificMiningScheduler(pool);self.simulation=ScientificSimulationGate(pool)
        self.methods=ScientificMethodRegistry()
        # Isolated observational plugin: writes versioned candidate evidence to
        # scientific_method_events; existing consensus/ML/simulation gates stay intact.
        self.book_tape=BookTapePaperLearner()
        self.methods.register(ScientificMethod(
            key="book_tape_research",version=BOOK_TAPE_VERSION,schema_version=1,
            handler=self.book_tape.observe,
            capabilities={"research_only":True,"live_orders":False,
                          "input_events":["trade_tape_250ms"],
                          "profile_kind":"bucket_close_proxy"}))
        self.last_mining_check=0.0;self.mining_runs=0;self.simulation_runs=0

    async def start(self):
        if self.started:return
        await register_consumer(self.pool,"market_events","scientific_research",required=False,active=True)
        await self.methods.sync_db(self.pool)
        row=await self.pool.fetchrow("""SELECT state,last_ts FROM observer_checkpoints
          WHERE observer='scientific_research' AND symbol='*'""")
        if row:
            state=_dict(row["state"]);self.last_id=int(state.get("last_id") or 0);self.last_event_ts=row["last_ts"]
        else:
            self.last_id=int(await self.pool.fetchval("SELECT COALESCE(max(id),0) FROM market_events") or 0)
            self.last_event_ts=await self.pool.fetchval("SELECT max(event_ts) FROM market_events")
            await self._checkpoint()
        # Hydrate only state known to be at-or-before the durable source checkpoint.
        await self._hydrate_features()
        await self._hydrate_micro_agents()
        self.started=True

    async def _hydrate_micro_agents(self):
        rows=await self.pool.fetch("""WITH ranked AS (
          SELECT symbol,event_ts,agent,state,score,direction,features,
                 row_number() OVER(PARTITION BY symbol,agent ORDER BY event_ts DESC) rn
          FROM micro_agent_signals WHERE event_ts>now()-interval '7 days'
            AND (source_event_id IS NULL OR source_event_id<=$1))
          SELECT symbol,event_ts,agent,state,score,direction,features
          FROM ranked WHERE rn<=600 ORDER BY symbol,agent,event_ts""",int(self.last_id))
        groups={}
        latest={}
        for r in rows:
            key=(str(r["symbol"]),str(r["agent"]))
            features=_dict(r["features"])
            groups.setdefault(key,[]).append((r,features))
            latest[key]=(r,features)
        mapping={
            "oi":(self.orchestrator.oi_agent,"oi_return_per_s"),
            "delta":(self.orchestrator.delta_agent,"delta_ratio"),
            "book_velocity":(self.orchestrator.book_agent,"book_update_rate"),
            "large_order":(self.orchestrator.wall_agent,"wall_ratio"),
            "volume":(self.orchestrator.volume_agent,"volume"),
        }
        for (symbol,agent_name),items in groups.items():
            pair=mapping.get(agent_name)
            if pair is not None:
                agent,key=pair
                agent.restore(symbol,[f.get(key) for _,f in items if f.get(key) is not None])
            row,features=items[-1]
            if agent_name=="oi" and features.get("oi") is not None:
                self.orchestrator.oi_agent.restore_prev(
                    symbol,int(row["event_ts"].timestamp()*1000),features["oi"])
            self.orchestrator.consensus.last[symbol][agent_name]=MicroSignal(
                agent_name,symbol,int(row["event_ts"].timestamp()*1000),str(row["state"]),
                float(row["score"]),int(row["direction"]),features)

    async def _hydrate_features(self):
        # Minute features describe a completed window, but ts is its start.
        # Without a source checkpoint there is no safe availability bound.
        if self.last_event_ts is None:
            return
        rows=await self.pool.fetch("""WITH ranked AS (
          SELECT symbol,ts,quality_status,features,
                 row_number() OVER(PARTITION BY symbol ORDER BY ts DESC) rn
          FROM market_features_1m WHERE eligible=true AND quality_status='GOOD'
            AND ts<=$1::timestamptz - interval '1 minute')
          SELECT symbol,ts,quality_status,features FROM ranked WHERE rn<=128
          ORDER BY symbol,ts""",self.last_event_ts)
        for r in rows:
            if r["ts"]+datetime.timedelta(minutes=1)>self.last_event_ts:
                continue
            features=_dict(r["features"])
            ts_ms=int(r["ts"].timestamp()*1000)
            self.orchestrator.ingest_feature_row(r["symbol"],ts_ms,features,r["quality_status"],"market_features_1m")

    async def _checkpoint(self):
        state=json.dumps({"last_id":int(self.last_id),"processed":int(self.processed),
                          "scheduled":int(self.scheduled),"errors":int(self.errors)},separators=(",",":"))
        await self.pool.execute("""INSERT INTO observer_checkpoints(observer,symbol,last_ts,state)
          VALUES('scientific_research','*',$1,$2::jsonb)
          ON CONFLICT(observer,symbol) DO UPDATE SET last_ts=EXCLUDED.last_ts,
          state=EXCLUDED.state,updated_at=now()""",self.last_event_ts,state)

    def ingest_feature_row(self,row,built):
        ts=built.get("ts") or row.get("ts")
        ts_ms=int(ts.timestamp()*1000) if hasattr(ts,"timestamp") else int(ts)
        return self.orchestrator.ingest_feature_row(
            row["symbol"],ts_ms,built.get("features") or {},
            built.get("quality_status") or row.get("quality_status","UNKNOWN"),"live_unified")

    async def run_once(self):
        if not self.started:await self.start()
        rows=await self.pool.fetch("""SELECT id,symbol,event_ts,event_type,payload FROM market_events
          WHERE id>$1 ORDER BY id LIMIT $2""",int(self.last_id),int(self.batch_size))
        if not rows:return 0
        watermarks={}
        for r in rows:
            payload=_dict(r["payload"]);ts_ms=int(r["event_ts"].timestamp()*1000)
            split_key=_split_key(r["event_ts"])
            result=await route_market_event(
                self.orchestrator,self.pool,r["symbol"],ts_ms,r["event_type"],payload,split_key,int(r["id"]))
            # Optional scientific plugins are fault-isolated: their failure is
            # journaled/quarantined and cannot block the core event checkpoint.
            await self.methods.dispatch(self.pool,{
                "source_event_id":int(r["id"]),"symbol":r["symbol"],"event_ts":r["event_ts"],
                "event_type":r["event_type"],"payload":payload,"split_key":split_key})
            self.processed+=1;self.scheduled+=int(result.get("scheduled") or 0)
            self.last_id=int(r["id"]);self.last_event_ts=r["event_ts"]
            watermarks[r["symbol"]]=r["event_ts"]
        await self._checkpoint()
        await set_consumer_watermarks(self.pool,[
            ("market_events","scientific_research",sym,ts,False) for sym,ts in watermarks.items()])
        return len(rows)

    async def run(self):
        await self.start()
        while not self.stop_event.is_set():
            try:
                n=await self.run_once()
                now=time.monotonic()
                if now-self.last_mining_check>=3600:
                    mined=await self.mining.run_closed_split_once()
                    self.mining_runs+=len(mined.get("runs") or [])
                    cutoff=mined["dataset_cutoff"]
                    await self.simulation.enqueue_validated(cutoff)
                    simulated=await self.simulation.run_queued(limit=2)
                    self.simulation_runs+=len(simulated)
                    self.last_mining_check=now
                if not n:await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors+=1
                log.exception("scientific consumer failed",extra={"event":"scientific_consumer_failed"})
                await asyncio.sleep(max(1.0,self.poll_seconds))

    def stop(self):self.stop_event.set()

    def status(self):
        lag=None
        if self.last_event_ts is not None:
            lag=max(0.0,time.time()-self.last_event_ts.timestamp())
        return {"started":self.started,"last_event_id":int(self.last_id),
                "processed":int(self.processed),"scheduled_outcomes":int(self.scheduled),
                "errors":int(self.errors),"mining_runs":int(self.mining_runs),
                "simulation_runs":int(self.simulation_runs),
                "lag_seconds":round(lag,2) if lag is not None else None}

def _split_key(ts):
    iso=ts.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def _dict(v):
    if isinstance(v,dict):return v
    if isinstance(v,str):
        try:
            x=json.loads(v);return x if isinstance(x,dict) else {}
        except (ValueError,TypeError):return {}
    try:return dict(v) if v is not None else {}
    except (TypeError,ValueError):return {}
