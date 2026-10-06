"""Scientific discovery layer for market-state geometry.

Research-only. 3-D coordinates are an interpretable view; hypothesis scoring
uses the full standardized feature vector. No function in this module can trade.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean
from .scientific_surfaces import PolynomialSurfaceTracker

@dataclass(frozen=True)
class ScientificPoint:
    symbol:str
    event_ts_ms:int
    vector:tuple[float,...]
    feature_names:tuple[str,...]
    projection3d:tuple[float,float,float]
    source:str
    quality:str="GOOD"

def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _norm(a):return sqrt(_dot(a,a))

class OnlineStandardizer:
    """Past-only Welford normalization with a frozen research epoch."""
    def __init__(self,freeze_after=256):
        self.n=0;self.mu=[];self.m2=[];self.freeze_after=max(2,int(freeze_after))
    def transform_then_update(self,row):
        x=[float(v) for v in row]
        if not self.mu:self.mu=[0.0]*len(x);self.m2=[0.0]*len(x)
        if len(x)!=len(self.mu):raise ValueError("feature dimension changed")
        z=[(v-self.mu[i])/sqrt(self.m2[i]/max(self.n-1,1)) if self.n>1 and self.m2[i]>1e-18 else 0.0 for i,v in enumerate(x)]
        if self.n<self.freeze_after:
            self.n+=1
            for i,v in enumerate(x):
                d=v-self.mu[i];self.mu[i]+=d/self.n;self.m2[i]+=d*(v-self.mu[i])
        return z
    @property
    def ready(self):return self.n>=self.freeze_after

class StreamingProjection3D:
    """Past-trained 3-D projection frozen after a bounded warmup epoch."""
    def __init__(self,dim,lr=.01,freeze_after=256):
        self.dim=int(dim);self.lr=float(lr);self.n=0;self.freeze_after=max(2,int(freeze_after))
        self.axes=[]
        for k in range(3):
            a=[0.0]*self.dim;a[k%self.dim]=1.0;self.axes.append(a)
    def project_then_update(self,z):
        if len(z)!=self.dim:raise ValueError("feature dimension changed")
        coords=tuple(_dot(z,a) for a in self.axes)
        if self.n>=self.freeze_after:return coords
        for k in range(3):
            a=self.axes[k]; y=_dot(z,a)
            a=[a[i]+self.lr*y*(z[i]-y*a[i]) for i in range(self.dim)]
            for j in range(k):
                q=self.axes[j];d=_dot(a,q);a=[u-d*v for u,v in zip(a,q)]
            n=_norm(a)
            if n>1e-12:a=[u/n for u in a]
            self.axes[k]=a
        self.n+=1
        return coords
    @property
    def ready(self):return self.n>=self.freeze_after

def polynomial_terms3(p,degree=3):
    """Monomials in x,y,z through degree 3: affine, conic and cubic geometry."""
    x,y,z=map(float,p);terms=[1.0,x,y,z]
    if degree>=2:terms += [x*x,y*y,z*z,x*y,x*z,y*z]
    if degree>=3:terms += [x*x*x,y*y*y,z*z*z,x*x*y,x*x*z,y*y*x,y*y*z,z*z*x,z*z*y,x*y*z]
    return terms

def geometric_invariants(points):
    """Coordinate-robust local descriptors; candidates, never trading signals."""
    pts=[tuple(map(float,p)) for p in points]
    if len(pts)<3:return {"samples":len(pts)}
    steps=[sqrt(sum((b[i]-a[i])**2 for i in range(3))) for a,b in zip(pts,pts[1:])]
    chords=[sqrt(sum((pts[i+2][j]-pts[i][j])**2 for j in range(3))) for i in range(len(pts)-2)]
    bend=[]
    for a,b,c in zip(pts,pts[1:],pts[2:]):
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-b[i] for i in range(3)]
        nu,nv=_norm(u),_norm(v)
        bend.append(0.0 if nu*nv<=1e-18 else max(-1.0,min(1.0,_dot(u,v)/(nu*nv))))
    return {"samples":len(pts),"path_length":sum(steps),"mean_step":mean(steps),
            "mean_chord2":mean(chords),"mean_turn_cos":mean(bend),
            "tortuosity":sum(steps)/max(sqrt(sum((pts[-1][i]-pts[0][i])**2 for i in range(3))),1e-12)}

class ScientificGeometryEngine:
    def __init__(self,feature_names,projection_lr=.01,warmup=256):
        self.names=tuple(feature_names);self.projection_lr=float(projection_lr);self.warmup=max(2,int(warmup))
        self.scalers={};self.projections={};self.history={}
        self.surface2={};self.surface3={};self.surface_state={}
    def ingest(self,symbol,event_ts_ms,features,source="unified",quality="GOOD"):
        if quality!="GOOD":return None
        try:x=[float(features[n]) for n in self.names]
        except (KeyError,TypeError,ValueError):return None
        scaler=self.scalers.setdefault(str(symbol),OnlineStandardizer(self.warmup))
        projection=self.projections.setdefault(str(symbol),StreamingProjection3D(len(self.names),self.projection_lr,self.warmup))
        z=scaler.transform_then_update(x)
        xyz=projection.project_then_update(z)
        point=ScientificPoint(str(symbol),int(event_ts_ms),tuple(z),self.names,xyz,str(source),str(quality))
        h=self.history.setdefault(str(symbol),[]);h.append(point)
        if len(h)>4096:del h[:-4096]
        return point
    def diagnostics(self,symbol,window=128):
        h=self.history.get(str(symbol),[])[-max(3,int(window)):]
        out=geometric_invariants([p.projection3d for p in h])
        scaler=self.scalers.get(str(symbol));projection=self.projections.get(str(symbol))
        out["projection_ready"]=bool(scaler and projection and scaler.ready and projection.ready)
        out["research_epoch_samples"]=int(scaler.n if scaler else 0)
        return out
