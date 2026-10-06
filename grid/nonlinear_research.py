"""Research-only nonlinear time-series tools inspired by Loskutov/Mikhailov §33.

These functions deliberately do not produce orders or promotion decisions.
They generate falsifiable research candidates for walk-forward evaluation.
"""
from __future__ import annotations
from math import sqrt

def delay_vectors(series,p,lag=1,horizon=1):
    p=int(p);lag=int(lag);horizon=int(horizon)
    if p<1 or lag<1 or horizon<1:raise ValueError("p, lag and horizon must be positive")
    x=[float(v) for v in series]
    start=(p-1)*lag
    out=[]
    for t in range(start,len(x)-horizon):
        out.append(([x[t-i*lag] for i in range(p)],x[t+horizon],t))
    return out

def _dist(a,b):
    return sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def local_analog_forecast(series,p=4,lag=1,horizon=1,k=20,theiler=10):
    """LA0 analogue forecast: median/mean-like local evolution without fitting a global model."""
    rows=delay_vectors(series,p,lag,horizon)
    if not rows:return None
    start=[float(series[-1-i*lag]) for i in range(p)]
    last_index=len(series)-1
    candidates=[( _dist(start,v),target,t) for v,target,t in rows
                if last_index-t>max(int(theiler),horizon)]
    candidates.sort(key=lambda z:z[0])
    near=candidates[:max(1,int(k))]
    if not near:return None
    # Distance weighting keeps exact/very close analogues dominant while remaining stable.
    eps=1e-12; weights=[1/(d+eps) for d,_,_ in near]; total=sum(weights)
    forecast=sum(w*y for w,(_,y,_) in zip(weights,near))/total
    return {"forecast":forecast,"neighbors":len(near),
            "mean_distance":sum(d for d,_,_ in near)/len(near),
            "p":int(p),"lag":int(lag),"horizon":int(horizon)}

def analog_direction_edge(series,p=4,lag=1,horizon=1,k=20,theiler=10):
    """Estimate only direction tendency; safer research target for noisy market series."""
    rows=delay_vectors(series,p,lag,horizon)
    if not rows:return None
    start=[float(series[-1-i*lag]) for i in range(p)]
    last_index=len(series)-1
    candidates=[]
    for v,target,t in rows:
        if last_index-t<=max(int(theiler),horizon):continue
        origin=v[0]; move=target-origin
        candidates.append((_dist(start,v),1 if move>0 else -1 if move<0 else 0))
    candidates.sort(key=lambda z:z[0]); near=candidates[:max(1,int(k))]
    if not near:return None
    edge=sum(direction for _,direction in near)/len(near)
    return {"direction_edge":edge,"neighbors":len(near),"p":int(p),"lag":int(lag),"horizon":int(horizon)}

def walk_forward_analog(series,p=4,lag=1,horizon=1,k=20,theiler=10,min_train=200):
    """Strict past-only evaluation: no future vector can become a neighbor."""
    x=[float(v) for v in series]; results=[]
    warm=max(int(min_train),(int(p)-1)*int(lag)+int(horizon)+2)
    for end in range(warm,len(x)-int(horizon)):
        hist=x[:end+1]
        pred=local_analog_forecast(hist,p,lag,horizon,k,theiler)
        if pred is None:continue
        actual=x[end+int(horizon)]
        results.append({"origin_index":end,"forecast":pred["forecast"],"actual":actual,
                        "error":pred["forecast"]-actual,"neighbors":pred["neighbors"]})
    return results
