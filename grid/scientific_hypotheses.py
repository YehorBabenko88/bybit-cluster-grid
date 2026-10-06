"""Scientific hypothesis lifecycle and independent-replication rules.

Research-only: VALIDATED means "eligible for simulation", never "trade now".
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
import json

STATES=("CANDIDATE","OBSERVED","REPLICATED","VALIDATED","REJECTED")

@dataclass(frozen=True)
class HypothesisSpec:
    method:str
    pattern:str
    horizon_ms:int
    direction:int
    feature_version:str
    parameters:dict
    research_only:bool=True
    def canonical(self):
        return {"method":self.method,"pattern":self.pattern,"horizon_ms":int(self.horizon_ms),
                "direction":int(self.direction),"feature_version":self.feature_version,
                "parameters":self.parameters,"research_only":True}
    def fingerprint(self):
        raw=json.dumps(self.canonical(),sort_keys=True,separators=(",",":")).encode()
        return sha256(raw).hexdigest()

@dataclass(frozen=True)
class Evidence:
    experiment_key:str
    symbol:str
    regime:str
    split_key:str
    sample_count:int
    mean_return_bps:float
    hit_rate:float
    cost_bps:float=0.0
    dataset_cutoff:str|None=None
    details:dict|None=None
    @property
    def net_edge_bps(self):return float(self.mean_return_bps)-float(self.cost_bps)

def evidence_passes(spec,e,min_samples=30,min_edge_bps=0.5,min_hit_rate=0.52):
    if int(e.sample_count)<int(min_samples):return False
    signed=float(e.net_edge_bps)*(1 if spec.direction>=0 else -1)
    return signed>=float(min_edge_bps) and float(e.hit_rate)>=float(min_hit_rate)

def lifecycle(spec,evidence,min_samples=30,min_edge_bps=.5,min_hit_rate=.52):
    # experiment_key uniqueness is enforced here and in DB. Re-running the same
    # split cannot manufacture replication.
    unique={e.experiment_key:e for e in evidence}
    ev=list(unique.values())
    passed=[e for e in ev if evidence_passes(spec,e,min_samples,min_edge_bps,min_hit_rate)]
    failed=[e for e in ev if int(e.sample_count)>=min_samples and e not in passed]
    if len(ev)>=3 and len(failed)/len(ev)>=2/3:return "REJECTED"
    if not passed:return "CANDIDATE"
    independent_splits={e.split_key for e in passed}
    symbols={e.symbol for e in passed}
    regimes={e.regime for e in passed}
    total=sum(int(e.sample_count) for e in passed)
    if len(passed)>=3 and len(independent_splits)>=3 and len(symbols)>=2 and len(regimes)>=2 and total>=200:
        return "VALIDATED"
    if len(passed)>=2 and len(independent_splits)>=2 and (len(symbols)>=2 or len(regimes)>=2):
        return "REPLICATED"
    return "OBSERVED"
