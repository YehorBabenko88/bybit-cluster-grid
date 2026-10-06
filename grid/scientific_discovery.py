"""Coordinates independent research methods without contaminating live ingestion."""
from __future__ import annotations
from collections import defaultdict,deque
from .scientific_geometry import ScientificGeometryEngine,polynomial_terms3
from .stochastic_research import lag1_autocorrelation,quadratic_variation
from .timeseries_research import volatility_regime

DEFAULT_FEATURES=("return_1m","realized_volatility","range_pct","volume_ratio","delta_ratio",
                  "close_vs_poc","poc_location","book_imbalance","spread","open_interest",
                  "funding_rate","basis_rate")

class ScientificDiscoveryEngine:
    """One-way research consumer: feature rows -> hypotheses -> future outcomes."""
    def __init__(self,feature_names=DEFAULT_FEATURES,max_history=4096):
        self.geometry=ScientificGeometryEngine(feature_names)
        self.max_history=max(256,int(max_history));self.series=defaultdict(lambda:deque(maxlen=self.max_history))
        self.last_ts={}
    def ingest_feature_row(self,symbol,ts_ms,features,quality="GOOD",source="unified"):
        ts=int(ts_ms);prev=self.last_ts.get(symbol)
        if prev is not None and ts<=prev:return {"accepted":False,"reason":"non_monotonic_event_time"}
        self.last_ts[symbol]=ts
        p=self.geometry.ingest(symbol,ts,features,source,quality)
        if p is None:return {"accepted":False,"reason":"quality_or_missing_features"}
        r=float(features.get("return_1m") or 0.0);self.series[symbol].append(r)
        diag=self.geometry.diagnostics(symbol)
        s=list(self.series[symbol])
        diag.update({"return_lag1_acf":lag1_autocorrelation(s),
                     "quadratic_variation":quadratic_variation([1.0]+_index_path(s)),
                     "volatility_regime":volatility_regime(s),
                     "poly3_terms":polynomial_terms3(p.projection3d,3)})
        return {"accepted":True,"point":p,"diagnostics":diag}

def _index_path(returns):
    p=1.0;out=[]
    for r in returns:p*=max(1e-12,1.0+float(r));out.append(p)
    return out
