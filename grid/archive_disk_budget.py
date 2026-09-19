import shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class DiskBudget:
    min_free_gb:float=10.0
    reserve_ratio:float=.10
    max_single_archive_gb:float=4.0

def archive_allowed(path,expected_bytes=None,policy=DiskBudget()):
    u=shutil.disk_usage(path)
    free_after=u.free-(int(expected_bytes) if expected_bytes else 0)
    required=max(int(policy.min_free_gb*1024**3),int(u.total*policy.reserve_ratio))
    if expected_bytes and expected_bytes>policy.max_single_archive_gb*1024**3:
        return False,{"reason":"archive_too_large","free":u.free,"required":required}
    if free_after<required:
        return False,{"reason":"disk_reserve","free":u.free,"free_after":free_after,"required":required}
    return True,{"reason":None,"free":u.free,"free_after":free_after,"required":required}
