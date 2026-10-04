from __future__ import annotations
import os,shutil,time
from pathlib import Path
from .content_cache import ContentAddressedCache
from .config import settings
from .archive_compute_queue import cleanup_stale_archive_partials


def cleanup_stale_workspaces(root,ttl_seconds):
    root=Path(root)
    if not root.exists():return {"deleted":0}
    cutoff=time.time()-float(ttl_seconds);deleted=0
    for p in root.iterdir():
        if not p.is_dir():continue
        try:mtime=p.stat().st_mtime
        except FileNotFoundError:continue
        if mtime>=cutoff:continue
        # Only service-owned scratch directories are eligible.
        if not (p.name.startswith("grid-strattester-") or p.name.startswith("grid-archive-compute-")):
            continue
        shutil.rmtree(p,ignore_errors=True);deleted+=1
    return {"deleted":deleted}


def maintenance_once():
    cache=ContentAddressedCache(settings.content_cache_root)
    cache_result=cache.gc(
        int(settings.content_cache_max_gb*1024**3),
        int(settings.content_cache_ttl_days*86400))
    workspace_root=Path(os.getenv("TEMP") or os.getenv("TMP") or ".")
    workspace_result=cleanup_stale_workspaces(workspace_root,int(settings.workspace_ttl_hours*3600))
    # Partial files can survive abrupt process/OS termination outside TemporaryDirectory cleanup.
    partials=0
    cache_root=Path(settings.content_cache_root)
    cutoff=__import__("time").time()-int(settings.workspace_ttl_hours*3600)
    for p in cache_root.rglob("*.part") if cache_root.exists() else []:
        try:
            if p.stat().st_mtime<cutoff:p.unlink();partials+=1
        except FileNotFoundError:pass
    return {"cache":cache_result,"workspaces":workspace_result,"partials_deleted":partials}
