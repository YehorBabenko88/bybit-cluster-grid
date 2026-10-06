"""Research-only stochastic diagnostics for market microstructure streams.

The module estimates properties of observed event streams; it has no order path.
"""
from __future__ import annotations
from math import cos,pi,sin,sqrt
from statistics import mean

def lag1_autocorrelation(values):
    x=[float(v) for v in values]
    if len(x)<3:return None
    m=mean(x); den=sum((v-m)**2 for v in x)
    return 0.0 if den<=1e-18 else sum((x[i]-m)*(x[i-1]-m) for i in range(1,len(x)))/den

def poisson_event_diagnostics(event_ts_ms):
    """For order/cancel/trade arrivals: rate plus dispersion of interval counts."""
    ts=sorted(int(t) for t in event_ts_ms)
    if len(ts)<3:return {"count":len(ts),"rate_per_s":0.0,"cv_interarrival":None}
    gaps=[max((b-a)/1000.0,1e-9) for a,b in zip(ts,ts[1:])]
    mg=mean(gaps); var=sum((g-mg)**2 for g in gaps)/len(gaps)
    return {"count":len(ts),"rate_per_s":1.0/mg,"cv_interarrival":sqrt(var)/mg,
            "lag1_gap_acf":lag1_autocorrelation(gaps)}

def markov_transition_matrix(states):
    labels=sorted(set(states)); counts={a:{b:0 for b in labels} for a in labels}
    for a,b in zip(states,states[1:]):counts[a][b]+=1
    return {a:{b:(counts[a][b]/max(sum(counts[a].values()),1)) for b in labels} for a in labels}

def spectral_band_power(values,bands=((0.0,.1),(.1,.3),(.3,.5))):
    """Small dependency-free periodogram on normalized Nyquist frequency [0,.5]."""
    x=[float(v) for v in values]
    n=len(x)
    if n<8:return []
    m=mean(x); x=[v-m for v in x]; out=[]
    powers=[]
    for k in range(1,n//2+1):
        re=sum(v*cos(2*pi*k*j/n) for j,v in enumerate(x))
        im=-sum(v*sin(2*pi*k*j/n) for j,v in enumerate(x))
        powers.append((k/n,(re*re+im*im)/n))
    total=sum(p for _,p in powers) or 1.0
    for lo,hi in bands:
        p=sum(p for f,p in powers if lo<=f<hi)
        out.append({"lo":lo,"hi":hi,"power_share":p/total})
    return out

def quadratic_variation(prices):
    """Realized path variation; useful as a stochastic-volatility research target."""
    p=[float(v) for v in prices if float(v)>0]
    if len(p)<2:return 0.0
    import math
    r=[math.log(b/a) for a,b in zip(p,p[1:])]
    return sum(v*v for v in r)
