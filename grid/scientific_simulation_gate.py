"""Promotion gate from VALIDATED research to deterministic simulation only."""
from __future__ import annotations
import json,uuid
from .scientific_pattern_miner import PatternObservation,tokens,strength_bucket,independent_bucket
from .scientific_simulation import (SimulationConfig,simulate_rows,
    deterministic_bootstrap_drawdowns,promotion_decision,config_json)

SIMULATION_VERSION="scientific-sim-v1"

class ScientificSimulationGate:
    def __init__(self,pool,config=None):
        self.pool=pool;self.config=config or SimulationConfig()

    async def enqueue_validated(self,dataset_cutoff):
        rows=await self.pool.fetch("""SELECT id FROM scientific_hypotheses
          WHERE status='VALIDATED' AND research_only=true""")
        made=0
        for r in rows:
            tag=await self.pool.execute("""INSERT INTO scientific_simulation_runs(
              id,hypothesis_id,simulation_version,config,dataset_cutoff)
              VALUES($1,$2,$3,$4::jsonb,$5)
              ON CONFLICT(hypothesis_id,simulation_version,dataset_cutoff) DO NOTHING""",
              uuid.uuid4(),r["id"],SIMULATION_VERSION,config_json(self.config),dataset_cutoff)
            if str(tag).endswith("1"):made+=1
        return made

    async def run_queued(self,limit=4):
        out=[]
        for _ in range(max(1,int(limit))):
            # A single atomic UPDATE claims the oldest available job across workers.
            # SKIP LOCKED prevents another worker from selecting the same row.
            r=await self.pool.fetchrow("""UPDATE scientific_simulation_runs AS target
              SET status='RUNNING',started_at=now()
              WHERE target.id=(
                SELECT id FROM scientific_simulation_runs
                WHERE status='QUEUED' ORDER BY created_at,id
                FOR UPDATE SKIP LOCKED LIMIT 1
              )
              RETURNING target.id,target.hypothesis_id,target.dataset_cutoff""")
            if r is None:break
            out.append(await self.run_one(r["id"],r["hypothesis_id"],r["dataset_cutoff"],claimed=True))
        return out

    async def run_one(self,run_id,hypothesis_id,dataset_cutoff,claimed=False):
        if not claimed:
            row=await self.pool.fetchrow("""UPDATE scientific_simulation_runs
              SET status='RUNNING',started_at=now()
              WHERE id=$1 AND status='QUEUED' RETURNING id""",run_id)
            if row is None:
                return {"run_id":str(run_id),"status":"NOT_CLAIMED"}
        oos_start=await self.pool.fetchval("""SELECT max(dataset_cutoff)
          FROM scientific_hypothesis_evidence WHERE hypothesis_id=$1 AND passed=true""",hypothesis_id)
        if oos_start is None:
            return await self._waiting(run_id,"validated hypothesis has no fixed evidence cutoff")
        await self.pool.execute("UPDATE scientific_simulation_runs SET oos_start=$2 WHERE id=$1",run_id,oos_start)
        h=await self.pool.fetchrow("""SELECT method,pattern,horizon_ms,direction,definition,status
          FROM scientific_hypotheses WHERE id=$1""",hypothesis_id)
        if not h or str(h["status"])!="VALIDATED":
            return await self._fail(run_id,"hypothesis is no longer VALIDATED")
        if str(h["method"])!="combinatorial-v1":
            return await self._waiting(run_id,f"exact simulation matcher unavailable for method {h['method']}")
        definition=_dict(h["definition"]);params=definition.get("parameters") or {}
        wanted=set(str(x) for x in params.get("tokens") or ())
        rows=await self.pool.fetch("""SELECT symbol,event_ts_ms,return_bps,payload
          FROM scientific_outcome_requests WHERE status='DONE' AND horizon_ms=$1
            AND to_timestamp(event_ts_ms/1000.0)>$2
            AND to_timestamp(observed_ts_ms/1000.0)<=$3
            AND event_type='micro_geometry_consensus' ORDER BY event_ts_ms""",
            int(h["horizon_ms"]),oos_start,dataset_cutoff)
        matched=[];seen=set();embargo=max(int(h["horizon_ms"]),5000)
        for r in rows:
            p=_dict(r["payload"]);raw=p.get("spec") or {};rp=raw.get("parameters") or {}
            try:
                if int(raw.get("direction",0))!=int(h["direction"]):continue
                o=PatternObservation(str(r["symbol"]),int(r["event_ts_ms"]),str(p.get("split_key","")),
                  str(p.get("regime","UNKNOWN")),str(p.get("geometry_bucket","UNKNOWN")),
                  int(raw["direction"]),tuple(str(x) for x in p.get("agents") or rp.get("agents") or ()),
                  strength_bucket(p.get("strength",rp.get("consensus_strength",0))),float(r["return_bps"]))
            except (KeyError,TypeError,ValueError):continue
            if str(h["method"])=="combinatorial-v1" and not wanted.issubset(set(tokens(o))):continue
            key=(o.symbol,independent_bucket(o.event_ts_ms,embargo))
            if key in seen:continue
            seen.add(key)
            matched.append({"symbol":o.symbol,"event_ts_ms":o.event_ts_ms,"split_key":o.split_key,
                            "return_bps":o.return_bps})
        if len(matched)<self.config.min_trades:
            return await self._waiting(run_id,f"insufficient OOS trades: {len(matched)}/{self.config.min_trades}")
        base=simulate_rows(matched,int(h["direction"]),int(h["horizon_ms"]),self.config,1.0)
        stress=simulate_rows(matched,int(h["direction"]),int(h["horizon_ms"]),self.config,1.75)
        mc=deterministic_bootstrap_drawdowns(
            [x["net_return_bps"] for x in base["trades"]],self.config.monte_carlo_paths,str(run_id),
            float(self.config.position_risk_fraction)/.005)
        passed,checks,p95=promotion_decision(base["metrics"],stress["metrics"],mc,self.config)
        for t in base["trades"]:
            await self.pool.execute("""INSERT INTO scientific_simulation_trades(
              run_id,ordinal,symbol,event_ts_ms,split_key,raw_return_bps,net_return_bps,
              fill_fraction,fee_bps,spread_bps,slippage_bps,latency_bps,funding_bps,equity_after)
              VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
              ON CONFLICT(run_id,ordinal) DO NOTHING""",run_id,t["ordinal"],t["symbol"],
              t["event_ts_ms"],t["split_key"],t["raw_return_bps"],t["net_return_bps"],
              t["fill_fraction"],t["fee_bps"],t["spread_bps"],t["slippage_bps"],t["latency_bps"],
              t["funding_bps"],t["equity_after"])
        metrics={**base["metrics"],"checks":checks,"monte_carlo_max_dd_p95":p95}
        status="SIMULATION_PASSED" if passed else "SIMULATION_FAILED"
        await self.pool.execute("""UPDATE scientific_simulation_runs SET status=$2,
          metrics=$3::jsonb,stress_metrics=$4::jsonb,reason=$5,completed_at=now() WHERE id=$1""",
          run_id,status,json.dumps(metrics,separators=(",",":")),
          json.dumps(stress["metrics"],separators=(",",":")),
          None if passed else "one or more promotion checks failed")
        return {"run_id":str(run_id),"status":status,"metrics":metrics,"stress":stress["metrics"]}

    async def _waiting(self,run_id,reason):
        await self.pool.execute("""UPDATE scientific_simulation_runs SET status='WAITING_OOS',
          reason=$2,completed_at=now() WHERE id=$1""",run_id,str(reason))
        return {"run_id":str(run_id),"status":"WAITING_OOS","reason":str(reason)}

    async def _fail(self,run_id,reason):
        await self.pool.execute("""UPDATE scientific_simulation_runs SET status='SIMULATION_FAILED',
          reason=$2,completed_at=now() WHERE id=$1""",run_id,str(reason))
        return {"run_id":str(run_id),"status":"SIMULATION_FAILED","reason":str(reason)}

def _dict(v):
    if isinstance(v,dict):return v
    if isinstance(v,str):
        try:
            x=json.loads(v);return x if isinstance(x,dict) else {}
        except (ValueError,TypeError):return {}
    try:return dict(v) if v is not None else {}
    except (TypeError,ValueError):return {}
