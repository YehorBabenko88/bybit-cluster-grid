"""Causal polynomial-surface research on frozen 3-D market coordinates."""
from __future__ import annotations
from math import sqrt
from statistics import mean

def _dot(a,b):return sum(x*y for x,y in zip(a,b))

def surface_basis(x,y,degree):
    out=[1.0,float(x),float(y)]
    if int(degree)>=2:out += [x*x,x*y,y*y]
    if int(degree)>=3:out += [x*x*x,x*x*y,x*y*y,y*y*y]
    return out

def _solve_linear(a,b):
    n=len(b);m=[list(a[i])+[float(b[i])] for i in range(n)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(m[r][col]))
        if abs(m[pivot][col])<1e-12:return None
        m[col],m[pivot]=m[pivot],m[col]
        d=m[col][col];m[col]=[v/d for v in m[col]]
        for r in range(n):
            if r==col:continue
            f=m[r][col]
            if f:m[r]=[u-f*v for u,v in zip(m[r],m[col])]
    return [m[i][-1] for i in range(n)]

def fit_polynomial_surface(points,degree=2,ridge=1e-6):
    pts=[tuple(map(float,p)) for p in points]
    terms=len(surface_basis(0.0,0.0,degree))
    if len(pts)<max(terms*3,20):return None
    ata=[[0.0]*terms for _ in range(terms)];atb=[0.0]*terms
    for x,y,z in pts:
        row=surface_basis(x,y,degree)
        for i in range(terms):
            atb[i]+=row[i]*z
            for j in range(terms):ata[i][j]+=row[i]*row[j]
    for i in range(terms):ata[i][i]+=float(ridge)
    coef=_solve_linear(ata,atb)
    if coef is None:return None
    residuals=[]
    for x,y,z in pts:
        residuals.append(z-_dot(surface_basis(x,y,degree),coef))
    mu=mean(residuals);var=sum((r-mu)**2 for r in residuals)/len(residuals)
    return {"degree":int(degree),"coefficients":coef,"residual_mean":mu,
            "residual_sd":sqrt(max(var,0.0)),
            "rmse":sqrt(sum(r*r for r in residuals)/len(residuals))}

class PolynomialSurfaceTracker:
    """Scores the current point against a surface fitted only on earlier points."""
    def __init__(self,degree=2,window=128):
        self.degree=int(degree);self.window=max(32,int(window));self.points=[]
    def score_then_update(self,point):
        model=fit_polynomial_surface(self.points,self.degree)
        out={"ready":False,"degree":self.degree}
        if model is not None:
            x,y,z=map(float,point)
            pred=_dot(surface_basis(x,y,self.degree),model["coefficients"])
            residual=z-pred;sd=max(float(model["residual_sd"]),1e-9)
            out={**model,"ready":True,"prediction":pred,"residual":residual,
                 "residual_z":(residual-float(model["residual_mean"]))/sd}
        self.points.append(tuple(map(float,point)))
        if len(self.points)>self.window:del self.points[:-self.window]
        return out
