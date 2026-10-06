"""Bounded combinatorial pattern miner with walk-forward and multiplicity control.

Research-only. Mining can nominate hypotheses for simulation; it cannot emit orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from math import erfc,sqrt
import json,uuid
from .scientific_hypotheses import HypothesisSpec,Evidence
from .scientific_memory import register_hypothesis,record_evidence,negative_memory_active

@dataclass(frozen=True)
class PatternObservation:
    symbol:str
    split_key:str
    regime:str
    geometry:str
    direction:int
    agents:tuple[str,...]
    strength_bucket:str
    return_bps:float

def strength_bucket(v):
    x=abs(float(v))
    if x>=4:return "S4"
    if x>=3:return "S3"
    if x>=2:return "S2"
    return "S1"

def tokens(o:PatternObservation):
    out=[f"regime={o.regime}",f"geometry={o.geometry}",f"strength={o.strength_bucket}"]
    out += [f"agent={a}" for a in sorted(set(o.agents))]
    return tuple(sorted(out))

def generate_patterns(o,min_size=2,max_size=4,max_patterns=96):
    t=tokens(o);out=[]
    for k in range(max(1,int(min_size)),min(int(max_size),len(t))+1):
        for c in combinations(t,k):
            # Require at least one micro-agent token so pure regime/geometry labels
            # cannot masquerade as an order-flow discovery.
            if not any(x.startswith("agent=") for x in c):continue
            out.append(c)
            if len(out)>=int(max_patterns):return out
    return out

def directional_stats(values,direction,cost_bps=1.0):
    signed=[float(v)*(1 if int(direction)>=0 else -1)-float(cost_bps) for v in values]
    n=len(signed)
    if not n:return {"n":0,"mean_net_bps":0.0,"hit_rate":0.0,"z":0.0,"p_value":1.0}
    mu=sum(signed)/n
    hit=sum(1 for x in signed if x>0)/n
    if n<2:return {"n":n,"mean_net_bps":mu,"hit_rate":hit,"z":0.0,"p_value":1.0}
    var=sum((x-mu)**2 for x in signed)/(n-1)
    se=sqrt(max(var,0.0)/n)
    z=mu/se if se>1e-12 else (99.0 if mu>0 else -99.0 if mu<0 else 0.0)
    # one-sided H1: directional net edge > 0
    p=.5*erfc(z/sqrt(2.0))
    return {"n":n,"mean_net_bps":mu,"hit_rate":hit,"z":z,"p_value":max(0.0,min(1.0,p))}

def holm_adjust(p_values):
    n=len(p_values);out=[1.0]*n
    ordered=sorted(enumerate(p_values),key=lambda x:x[1]);running=0.0
    for rank,(idx,p) in enumerate(ordered):
        adj=min(1.0,(n-rank)*float(p));running=max(running,adj);out[idx]=running
    return out

class ScientificPatternMiner:
    def __init__(self,feature_version="scientific-v1",cost_bps=1.0,
                 min_samples=30,min_size=2,max_size=4,max_patterns_per_event=96):
        self.feature_version=str(feature_version);self.cost_bps=float(cost_bps)
        self.min_samples=max(5,int(min_samples));self.min_size=int(min_size);self.max_size=int(max_size)
        self.max_patterns_per_event=max(8,int(max_patterns_per_event))

    async def mine_split(self,pool,horizon_ms,split_key,dataset_cutoff):
        family=f"combinatorial-v1|h={int(horizon_ms)}|fv={self.feature_version}"
        run_id=uuid.uuid4()
        await pool.execute("""INSERT INTO scientific_mining_families(
          family_key,method,horizon_ms,feature_version) VALUES($1,'combinatorial-v1',$2,$3)
          ON CONFLICT(family_key) DO NOTHING""",family,int(horizon_ms),self.feature_version)
        await pool.execute("""INSERT INTO scientific_mining_runs(
          id,family_key,split_key,dataset_cutoff) VALUES($1,$2,$3,$4)""",
          run_id,family,str(split_key),dataset_cutoff)
        observations=await self._load(pool,horizon_ms,split_key,dataset_cutoff)
        grouped={}
        for o in observations:
            for pat in generate_patterns(o,self.min_size,self.max_size,self.max_patterns_per_event):
                key=(pat,int(o.direction),o.symbol,o.regime)
                grouped.setdefault(key,[]).append(float(o.return_bps))
        candidates=[]
        for (pat,direction,symbol,regime),vals in grouped.items():
            if len(vals)<self.min_samples:continue
            st=directional_stats(vals,direction,self.cost_bps)
            candidates.append((pat,direction,symbol,regime,st))
        prior_tests=int(await pool.fetchval(
            "SELECT hypotheses_tested FROM scientific_mining_families WHERE family_key=$1",family) or 0)
        adjusted=holm_adjust([x[4]["p_value"] for x in candidates])
        # Continuous research does not get a fresh alpha budget every week.
        # Inflate current Holm-adjusted p-values by the accumulated family search count.
        if prior_tests:
            factor=1.0+prior_tests/max(1,len(candidates))
            adjusted=[min(1.0,p*factor) for p in adjusted]
        accepted=0
        for item,p_adj in zip(candidates,adjusted):
            pat,direction,symbol,regime,st=item
            if p_adj>.05 or st["mean_net_bps"]<=.5 or st["hit_rate"]<.52:continue
            spec=HypothesisSpec("combinatorial-v1","&".join(pat),int(horizon_ms),int(direction),
                                self.feature_version,{"tokens":list(pat)})
            if await negative_memory_active(pool,spec):continue
            reg=await register_hypothesis(pool,spec)
            raw_mean=sum(grouped[(pat,direction,symbol,regime)])/len(grouped[(pat,direction,symbol,regime)])
            evidence=Evidence(
                f"{symbol}|{regime}|{split_key}|{int(horizon_ms)}|miner",symbol,regime,str(split_key),
                int(st["n"]),float(raw_mean),float(st["hit_rate"]),
                self.cost_bps,str(dataset_cutoff),
                {"p_value":st["p_value"],"corrected_p_value":p_adj,"effect_z":st["z"],
                 "family_key":family,"prior_family_tests":prior_tests,"mining_run_id":str(run_id)})
            await record_evidence(pool,reg["id"],spec,evidence)
            await pool.execute("""UPDATE scientific_hypothesis_evidence SET
              p_value=$3,corrected_p_value=$4,effect_z=$5
              WHERE hypothesis_id=$1 AND experiment_key=$2""",
              reg["id"],evidence.experiment_key,float(st["p_value"]),float(p_adj),float(st["z"]))
            accepted+=1
        await pool.execute("""UPDATE scientific_mining_families SET
          hypotheses_tested=hypotheses_tested+$2,last_run_at=now(),updated_at=now()
          WHERE family_key=$1""",family,len(candidates))
        await pool.execute("""UPDATE scientific_mining_runs SET candidate_count=$2,
          accepted_count=$3,status='DONE',completed_at=now() WHERE id=$1""",
          run_id,len(candidates),accepted)
        return {"run_id":str(run_id),"family_key":family,"observations":len(observations),
                "candidates":len(candidates),"accepted":accepted}

    async def _load(self,pool,horizon_ms,split_key,dataset_cutoff):
        rows=await pool.fetch("""SELECT symbol,return_bps,payload FROM scientific_outcome_requests
          WHERE status='DONE' AND horizon_ms=$1 AND payload->>'split_key'=$2
            AND to_timestamp(observed_ts_ms/1000.0)<=$3
            AND event_type='micro_geometry_consensus'""",int(horizon_ms),str(split_key),dataset_cutoff)
        out=[]
        for r in rows:
            p=_dict(r["payload"]);raw=p.get("spec") or {};params=raw.get("parameters") or {}
            try:
                out.append(PatternObservation(
                    str(r["symbol"]),str(split_key),str(p.get("regime","UNKNOWN")),
                    str(p.get("geometry_bucket","UNKNOWN")),int(raw["direction"]),
                    tuple(str(x) for x in p.get("agents") or params.get("agents") or ()),
                    strength_bucket(p.get("strength",params.get("consensus_strength",0))),
                    float(r["return_bps"])))
            except (KeyError,TypeError,ValueError):continue
        return out

def _dict(v):
    if isinstance(v,dict):return v
    if isinstance(v,str):
        try:
            x=json.loads(v);return x if isinstance(x,dict) else {}
        except (ValueError,TypeError):return {}
    try:return dict(v) if v is not None else {}
    except (TypeError,ValueError):return {}
