"""Dependency-light time-series research primitives.

These are diagnostics/candidate generators, never trading decisions.
"""
from __future__ import annotations
from math import sqrt
from statistics import mean

def acf(values,max_lag=20):
    x=[float(v) for v in values]
    if len(x)<3:return []
    m=mean(x); den=sum((v-m)**2 for v in x)
    if den<=1e-18:return [1.0]+[0.0]*min(max_lag,len(x)-1)
    return [1.0]+[sum((x[t]-m)*(x[t-h]-m) for t in range(h,len(x)))/den
                 for h in range(1,min(int(max_lag),len(x)-1)+1)]

def difference(values,order=1):
    x=[float(v) for v in values]
    for _ in range(max(0,int(order))):x=[b-a for a,b in zip(x,x[1:])]
    return x

def rolling_volatility(returns,window=30):
    x=[float(v) for v in returns];w=max(2,int(window));out=[]
    for i in range(len(x)):
        z=x[max(0,i-w+1):i+1];m=mean(z)
        out.append(sqrt(sum((v-m)**2 for v in z)/max(len(z),1)))
    return out

def distributed_lag_correlations(cause,effect,max_lag=20):
    """Exploratory lead/lag map. Correlation is not causality."""
    x=[float(v) for v in cause];y=[float(v) for v in effect];n=min(len(x),len(y));out=[]
    for lag in range(0,min(int(max_lag),n-3)+1):
        a=x[:n-lag] if lag else x[:n];b=y[lag:n]
        ma,mb=mean(a),mean(b);da=sum((v-ma)**2 for v in a);db=sum((v-mb)**2 for v in b)
        corr=0.0 if da*db<=1e-18 else sum((u-ma)*(v-mb) for u,v in zip(a,b))/sqrt(da*db)
        out.append({"lag":lag,"corr":corr})
    return out

def volatility_regime(returns,short=20,long=200):
    x=[float(v) for v in returns]
    if len(x)<max(short,3):return {"state":"WARMUP","ratio":None}
    def sd(z):
        m=mean(z);return sqrt(sum((v-m)**2 for v in z)/len(z))
    sv=sd(x[-short:]);lv=sd(x[-min(long,len(x)):])
    ratio=sv/max(lv,1e-12)
    return {"state":"HIGH" if ratio>=1.5 else "LOW" if ratio<=.67 else "NORMAL","ratio":ratio,
            "short_vol":sv,"long_vol":lv}

def pair_error_correction(x,y,window=500):
    """Simple research proxy for cointegration/error correction; not a formal test."""
    a=[float(v) for v in x][-window:];b=[float(v) for v in y][-window:];n=min(len(a),len(b))
    if n<30:return None
    a,b=a[-n:],b[-n:];mx,my=mean(a),mean(b);den=sum((v-mx)**2 for v in a)
    if den<=1e-18:return None
    beta=sum((u-mx)*(v-my) for u,v in zip(a,b))/den
    alpha=my-beta*mx;res=[v-alpha-beta*u for u,v in zip(a,b)]
    mr=mean(res);sd=sqrt(sum((r-mr)**2 for r in res)/n)
    return {"alpha":alpha,"beta":beta,"spread":res[-1],"z":(res[-1]-mr)/max(sd,1e-12),
            "residual_lag1_acf":acf(res,1)[1]}
