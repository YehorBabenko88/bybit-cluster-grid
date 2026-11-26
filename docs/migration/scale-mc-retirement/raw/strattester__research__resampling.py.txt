from __future__ import annotations
from dataclasses import dataclass
import random

@dataclass(frozen=True)
class BootstrapCI:
    lower:float
    mean:float
    upper:float

def _quantile(xs,q):
    if not xs: raise ValueError('empty sample')
    ys=sorted(xs)
    pos=(len(ys)-1)*q
    lo=int(pos); hi=min(lo+1,len(ys)-1); frac=pos-lo
    return ys[lo]*(1-frac)+ys[hi]*frac

def bootstrap_expectancy(values,*,iterations:int=1000,seed:int=0,confidence:float=.95)->BootstrapCI:
    xs=tuple(float(x) for x in values)
    if not xs: raise ValueError('empty sample')
    if iterations<1: raise ValueError('iterations must be positive')
    rng=random.Random(seed); means=[]
    for _ in range(iterations):
        draw=[xs[rng.randrange(len(xs))] for _ in xs]
        means.append(sum(draw)/len(draw))
    alpha=(1-confidence)/2
    return BootstrapCI(_quantile(means,alpha),sum(xs)/len(xs),_quantile(means,1-alpha))

def _max_drawdown(path):
    equity=0.0; peak=0.0; max_dd=0.0
    for x in path:
        equity+=x; peak=max(peak,equity); max_dd=max(max_dd,peak-equity)
    return max_dd

def monte_carlo_max_drawdowns(values,*,iterations:int=1000,seed:int=0):
    xs=list(float(x) for x in values)
    if not xs: raise ValueError('empty sample')
    rng=random.Random(seed); out=[]
    for _ in range(iterations):
        path=list(xs); rng.shuffle(path); out.append(_max_drawdown(path))
    return tuple(out)
