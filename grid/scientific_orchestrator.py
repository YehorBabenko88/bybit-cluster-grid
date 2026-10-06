"""End-to-end scientific research orchestrator.

Consumes research signals and feature context, schedules durable future labels,
and turns completed labels into independently replicated hypothesis evidence.
Never emits orders.
"""
from __future__ import annotations
from dataclasses import asdict
from .micro_agents import (MicrostructureConsensus,MicroSignal,OIAgent,DeltaAgent,
                           BookVelocityAgent,LargeOrderAgent,VolumeAgent)
from .scientific_discovery import ScientificDiscoveryEngine
from .scientific_hypotheses import HypothesisSpec,Evidence
from .scientific_memory import register_hypothesis,record_evidence,negative_memory_active
from .scientific_outcomes import schedule_outcomes,observe_price

class ScientificResearchOrchestrator:
    def __init__(self,feature_version="scientific-v1",horizons_s=(1,2,5,10,30,60),
                 min_agents=2,cost_bps=1.0,max_context_age_ms=120000):
        self.feature_version=str(feature_version)
        self.horizons_s=tuple(sorted({int(x) for x in horizons_s if int(x)>0}))
        self.consensus=MicrostructureConsensus(min_agents=min_agents)
        self.oi_agent=OIAgent();self.delta_agent=DeltaAgent()
        self.book_agent=BookVelocityAgent();self.wall_agent=LargeOrderAgent();self.volume_agent=VolumeAgent()
        self.discovery=ScientificDiscoveryEngine()
        self.latest_trade={}
        self.latest_context={}
        self.cost_bps=float(cost_bps);self.max_context_age_ms=max(0,int(max_context_age_ms))

    def ingest_feature_row(self,symbol,ts_ms,features,quality="GOOD",source="unified"):
        out=self.discovery.ingest_feature_row(symbol,ts_ms,features,quality,source)
        if out.get("accepted"):
            d=out["diagnostics"]
            vr=(d.get("volatility_regime") or {}).get("state","UNKNOWN")
            geom=_geometry_bucket(d)
            self.latest_context[str(symbol)]={"ts_ms":int(ts_ms),"regime":str(vr),
                "geometry_bucket":geom,"diagnostics":d}
        return out

    async def ingest_micro_signal(self,pool,signal:MicroSignal,reference_price,split_key):
        c=self.consensus.update(signal)
        if not c.get("candidate") or not c.get("direction"):
            return {"candidate":False,"consensus":c,"scheduled":0}
        symbol=str(signal.symbol);ctx=self.latest_context.get(symbol,{})
        fresh=bool(ctx) and int(signal.ts_ms)-int(ctx.get("ts_ms",0))<=self.max_context_age_ms
        regime=str(ctx.get("regime","UNKNOWN")) if fresh else "STALE_CONTEXT"
        geometry_bucket=str(ctx.get("geometry_bucket","UNKNOWN")) if fresh else "STALE_CONTEXT"
        agents=tuple(sorted(c.get("active_agents") or ()))
        pattern="+".join(agents)
        event_id=f"{symbol}:{int(signal.ts_ms)}:{pattern}:{int(c['direction'])}"
        scheduled=0;hypotheses=[]
        for h in self.horizons_s:
            spec=HypothesisSpec(
                method="micro_geometry_consensus",
                pattern=pattern,
                horizon_ms=h*1000,
                direction=int(c["direction"]),
                feature_version=self.feature_version,
                parameters={"agents":agents,"regime":regime,
                            "geometry_bucket":geometry_bucket,
                            "consensus_strength":round(float(c.get("strength") or 0),6)},
            )
            if await negative_memory_active(pool,spec):
                continue
            registered=await register_hypothesis(pool,spec)
            payload={"spec":spec.canonical(),"hypothesis_id":str(registered["id"]),
                     "split_key":str(split_key),"regime":regime,
                     "geometry_bucket":geometry_bucket,"agents":list(agents),
                     "strength":float(c.get("strength") or 0)}
            scheduled+=await schedule_outcomes(
                pool,event_id,spec.fingerprint(),symbol,int(signal.ts_ms),float(reference_price),
                "micro_geometry_consensus",payload,horizons_s=(h,))
            hypotheses.append({"id":str(registered["id"]),"fingerprint":spec.fingerprint(),
                               "horizon_ms":h*1000,"status":registered["status"]})
        return {"candidate":True,"consensus":c,"scheduled":scheduled,"hypotheses":hypotheses}

    async def observe_price(self,pool,symbol,ts_ms,price):
        labels=await observe_price(pool,symbol,ts_ms,price)
        updates=[]
        for label in labels:
            payload=label.get("payload") or {}
            raw=payload.get("spec") or {}
            try:
                spec=HypothesisSpec(str(raw["method"]),str(raw["pattern"]),int(raw["horizon_ms"]),
                    int(raw["direction"]),str(raw["feature_version"]),dict(raw.get("parameters") or {}))
                hypothesis_id=payload["hypothesis_id"]
                split_key=str(payload["split_key"]);regime=str(payload.get("regime","UNKNOWN"))
            except (KeyError,TypeError,ValueError):
                continue
            evidence=await _aggregate_evidence(
                pool,spec,label["hypothesis_fingerprint"],str(symbol),regime,split_key,
                self.cost_bps)
            if evidence is None:continue
            result=await record_evidence(pool,hypothesis_id,spec,evidence)
            updates.append({"fingerprint":spec.fingerprint(),**result})
        return {"labels":labels,"hypothesis_updates":updates}

async def _aggregate_evidence(pool,spec,fingerprint,symbol,regime,split_key,cost_bps):
    rows=await pool.fetch("""SELECT return_bps,observed_ts_ms FROM scientific_outcome_requests
      WHERE hypothesis_fingerprint=$1 AND symbol=$2 AND horizon_ms=$3 AND status='DONE'
        AND payload->>'regime'=$4 AND payload->>'split_key'=$5
      ORDER BY observed_ts_ms""",fingerprint,symbol,int(spec.horizon_ms),regime,split_key)
    if not rows:return None
    vals=[float(r["return_bps"]) for r in rows]
    direction=1 if spec.direction>=0 else -1
    hit=sum(1 for x in vals if x*direction>float(cost_bps))/len(vals)
    experiment_key=f"{symbol}|{regime}|{split_key}|{int(spec.horizon_ms)}"
    cutoff=max(int(r["observed_ts_ms"]) for r in rows)
    return Evidence(experiment_key,symbol,regime,split_key,len(vals),sum(vals)/len(vals),
                    hit,float(cost_bps),None,{"last_observed_ts_ms":cutoff})

def _geometry_bucket(d):
    if not d or "tortuosity" not in d:return "WARMUP"
    tort=float(d.get("tortuosity") or 0)
    turn=float(d.get("mean_turn_cos") or 0)
    if tort>=3:return "HIGH_TORTUOSITY"
    if turn>=.7:return "PERSISTENT"
    if turn<=-.2:return "REVERSING"
    return "MIXED"
