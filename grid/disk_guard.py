import pathlib
import shutil
from dataclasses import dataclass

NORMAL="NORMAL"
SOFT="SOFT"
HARD="HARD"
EMERGENCY="EMERGENCY"

@dataclass(frozen=True)
class DiskWatermarks:
    soft_free_gb:float=35.0
    hard_free_gb:float=20.0
    emergency_free_gb:float=8.0
    soft_free_ratio:float=.12
    hard_free_ratio:float=.07
    emergency_free_ratio:float=.03

def disk_state(path,policy=DiskWatermarks()):
    p=pathlib.Path(path)
    p.mkdir(parents=True,exist_ok=True)
    u=shutil.disk_usage(p)
    ratio=u.free/max(1,u.total)
    free_gb=u.free/(1024**3)
    if free_gb<policy.emergency_free_gb or ratio<policy.emergency_free_ratio:
        state=EMERGENCY
    elif free_gb<policy.hard_free_gb or ratio<policy.hard_free_ratio:
        state=HARD
    elif free_gb<policy.soft_free_gb or ratio<policy.soft_free_ratio:
        state=SOFT
    else:
        state=NORMAL
    return {"state":state,"free":u.free,"total":u.total,"free_gb":free_gb,"free_ratio":ratio}

def heavy_work_allowed(state):
    return state==NORMAL

def live_collection_allowed(state):
    return state not in (HARD,EMERGENCY)
