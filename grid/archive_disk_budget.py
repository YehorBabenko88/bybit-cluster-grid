import math
import shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class DiskBudget:
    min_free_gb:float=10.0
    reserve_ratio:float=.10
    max_single_archive_gb:float=4.0

def archive_allowed(path,expected_bytes=None,policy=DiskBudget()):
    if (not math.isfinite(policy.min_free_gb) or policy.min_free_gb<0
        or not math.isfinite(policy.reserve_ratio) or not 0<=policy.reserve_ratio<=1
        or not math.isfinite(policy.max_single_archive_gb) or policy.max_single_archive_gb<=0):
        raise ValueError("invalid archive disk budget policy")
    if expected_bytes is not None and (isinstance(expected_bytes,bool)
                                       or not isinstance(expected_bytes,int) or expected_bytes<=0):
        raise ValueError("expected archive bytes must be a positive integer or None")
    u=shutil.disk_usage(path)
    limit=int(policy.max_single_archive_gb*1024**3)
    if limit<1:
        raise ValueError("maximum archive size must be at least one byte")
    required=max(int(policy.min_free_gb*1024**3),int(u.total*policy.reserve_ratio))
    if expected_bytes is not None and expected_bytes>limit:
        return False,{"reason":"archive_too_large","free":u.free,"required":required}
    # Discovery commonly lacks Content-Length. Reserve the entire hard download cap
    # rather than assuming the archive will occupy zero bytes.
    reserve=limit if expected_bytes is None else (expected_bytes*105+99)//100
    free_after=u.free-reserve
    if free_after<required:
        return False,{"reason":"disk_reserve","free":u.free,"free_after":free_after,"required":required}
    return True,{"reason":None,"free":u.free,"free_after":free_after,"required":required}
