"""Workstream D (unified-system#154): Grid research modules duplicate Math.

grid/timeseries_research.py, grid/stochastic_research.py, grid/nonlinear_research.py
and scripts/history_ci.py are byte-identical copies of Math
(YehorBabenko88/math@9e6acbd9e12a91189f57234828e31640983af553)
python/history_timeseries.py, python/history_stochastic.py,
python/history_nonlinear.py and scripts/history_ci.py.

This guard proves it without installing Math:
1. git blob SHA of every Grid copy == pinned Math blob SHA (identical bytes);
2. Grid outputs on fixed, libm-free synthetic inputs reproduce SHA-256 digests
   computed from the Math modules at that revision (same inputs -> identical
   outputs, float repr exact). sin/cos/log-dependent outputs (spectral power,
   quadratic variation) are pinned separately so a platform libm difference is
   distinguishable from a code difference.

Removal/redirect is NOT done here: grid.scientific_discovery (production) imports
these modules, the Math wheel (pyproject py-modules) does not export
history_timeseries/history_stochastic/history_nonlinear, and the Grid bundle and
preflight do not install Math. Any edit to a Grid copy must fail this guard.
"""
import hashlib
import json
import math
import random
from pathlib import Path

import grid.nonlinear_research as nonlinear
import grid.stochastic_research as stochastic
import grid.timeseries_research as timeseries

ROOT = Path(__file__).resolve().parents[1]
MATH_REVISION = "9e6acbd9e12a91189f57234828e31640983af553"
PINNED_MATH_BLOBS = {
    "grid/timeseries_research.py": "44209867d0083fb9e19d50f7c871ad69aa2e4e76",  # math python/history_timeseries.py
    "grid/stochastic_research.py": "a494df163860b695fa46ff9b7e79067ebd2706ac",  # math python/history_stochastic.py
    "grid/nonlinear_research.py": "f65c91370957cb6fa8d7d3c025477f976e999206",  # math python/history_nonlinear.py
    "scripts/history_ci.py": "96cd7331204eb6b1f1087d3601e4160a4f8cd945",        # math scripts/history_ci.py
}
PURE_DIGESTS = {
    "0": "77d9e27e0ae3bac753935a1da8e021dd3d9096d2cc8369bfdd27ac359cc5fad4",
    "1": "fff5deea82cecc66c7f6160fe7baa6bda0e278575b9591cae89b7827ebde69e9",
    "10": "919f1f74123a8b7a0c2634d1a3c4d80f21a2bb01dd5b6dd4888c516703e8c0d7",
    "11": "3531bf1f0a94a9cacef09649c0bcd7971fb311972c1578164bce35a6d1d58a44",
    "2": "11f0a8b07db2a1daf0e026314fc87a9a2e1ec8a7c68fd4b5865dfcd79d8932d1",
    "3": "644efccf0d1934cfb13b354a2e1f231ec65f9383d578422ddeee5425928d22f2",
    "4": "a00931a94794c15b3fdce43d621937b8fcf24f5e537ed18fabaa9be943c08194",
    "5": "199b4a16f19539f692e2f0e4bc3a5847bc6e587ecae333dedfb1875a73310727",
    "6": "99f3be3fe923f22d8f8e7b1d34646513d260095daf0f86d0415734531f5624be",
    "7": "bca57b211203a7e424b891e811dbe0dcd562211c59eb54443520b8622562bf04",
    "8": "1c9014da65e20264bc8c8fa5171df5038fe14692ee8f015c906c6402ee1e3856",
    "9": "12974a25c12735519e7e041a302bd0439fd612373d9a26d8fa0545d793f56a5b",
    "edge": "5419d4e3f4122079450f93a8625fbe9b714c6e77b3dcaac815116969c2326096"
}
LIBM_DIGESTS = {
    "0": "39bfa3894e111c8914200eca7156227778dd25e77e83d505ed1ad685b38e258c",
    "1": "0e9d43e847aa7fe3a5ce8f03ac01034293c9da27d2c7f1e11a24ccff50a278a8",
    "10": "0a377fad3cc0619e61b18e965db47fe4f1f183af77e7769c27d507291281f06d",
    "11": "bfa262057934a9410ae956dc3d9ea453b96fa54f7400a0a79aca0f316758cd8e",
    "2": "a5a714c5b701ce90baa1a2a39bd064f89a3b6dba6c00673a0a17a1f1c84d091d",
    "3": "ca32332e4c0be6af206ebfeed0b7b7701c6baaa6329bc1c51316119c49704470",
    "4": "ee995c0c3e4c4ef3d121373984526aa272978ec5b754dbdab3779d24dc4076b6",
    "5": "1f81fad76d53cf28804e7468ad5ae4d228eba97b28acd0ead550ce409ea8ab44",
    "6": "fe2163515a25b40e0a19f16c517d42a3dd3c825ebca4903cb9fb8924eacd85f1",
    "7": "75960e521289f5725450da98e00b6d024bc1bb51d778ab0ab45643b4e29ff337",
    "8": "7b6d1f582aa746ecafa3b76cd43907f0aaf465b047e8dde1f751059866e94bab",
    "9": "70292048572b957de8b32ebff379057ae089218693a813bc4feaf44e77994657",
    "edge": "19e923e4104067f8090c6878569381805636ddebe9cb4086b4d91239aab5e754"
}
LIBM = {"spectral", "qv"}

# ---- deterministic vectors (identical code generated the Math digests) ----
def canon(x):
    if isinstance(x,bool) or x is None or isinstance(x,(int,str)):return x
    if isinstance(x,float):return {'f':repr(x)}
    if isinstance(x,(list,tuple)):return [canon(v) for v in x]
    if isinstance(x,dict):return {'d':[[canon(k),canon(v)] for k,v in sorted(x.items(),key=lambda kv:repr(kv[0]))]}
    raise TypeError(type(x))
def cases():
    out=[]
    for seed in range(12):
        r=random.Random(seed);n=r.choice((30,80,260,420))
        ret=[(r.random()-0.5)*0.02 for _ in range(n)]
        y=[100.0];[y.append(y[-1]*(1+v)) for v in ret]
        x=[v+(r.random()-0.5) for v in y]
        ts=sorted(r.randint(0,10**7) for _ in range(max(3,n//4)))
        states=[r.choice('ABC') for _ in range(n)]
        out.append(dict(seed=seed,ret=ret,price=y,x=x,ts=ts,states=states))
    out.append(dict(seed='edge',ret=[0.0]*5,price=[1.0,1.0,1.0],x=[1.0,1.0,1.0],ts=[5],states=['A']))
    return out
def run(ts_mod,st_mod,nl_mod):
    res=[]
    for c in cases():
        row={}
        def call(name,f,*a,**k):
            try:row[name]=canon(f(*a,**k))
            except Exception as e:row[name]={'raise':type(e).__name__}
        call('acf',ts_mod.acf,c['ret'],5)
        call('difference1',ts_mod.difference,c['price'])
        call('difference2',ts_mod.difference,c['price'],2)
        call('rolling_volatility',ts_mod.rolling_volatility,c['ret'],10)
        call('distributed_lag',ts_mod.distributed_lag_correlations,c['ret'],c['ret'][1:]+[0.0],4)
        call('volatility_regime',ts_mod.volatility_regime,c['ret'])
        call('volatility_regime_small',ts_mod.volatility_regime,c['ret'],5,20)
        call('pair_error_correction',ts_mod.pair_error_correction,c['x'],c['price'],50)
        call('lag1',st_mod.lag1_autocorrelation,c['ret'])
        call('poisson',st_mod.poisson_event_diagnostics,c['ts'])
        call('markov',st_mod.markov_transition_matrix,c['states'])
        call('spectral',st_mod.spectral_band_power,c['ret'][:128])
        call('qv',st_mod.quadratic_variation,c['price'])
        call('delay_vectors',nl_mod.delay_vectors,c['ret'][:60],3,2,1)
        call('analog_forecast',nl_mod.local_analog_forecast,c['ret'][:200],k=5,theiler=3)
        call('analog_edge',nl_mod.analog_direction_edge,c['ret'][:200],k=5,theiler=3)
        call('walk_forward',nl_mod.walk_forward_analog,c['ret'],k=5,theiler=3,min_train=20)
        res.append([str(c['seed']),row])
    return res


def _blob(path):
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _digests(keep):
    rows = run(timeseries, stochastic, nonlinear)
    return {seed: hashlib.sha256(json.dumps({k: v for k, v in row.items() if keep(k)},
                                             sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for seed, row in rows}


def test_grid_copies_are_byte_identical_to_pinned_math_sources():
    assert {path: _blob(path) for path in PINNED_MATH_BLOBS} == PINNED_MATH_BLOBS


def test_grid_outputs_equal_math_outputs_on_libm_free_vectors():
    assert _digests(lambda name: name not in LIBM) == PURE_DIGESTS


def test_grid_outputs_equal_math_outputs_on_libm_vectors():
    assert _digests(lambda name: name in LIBM) == LIBM_DIGESTS
