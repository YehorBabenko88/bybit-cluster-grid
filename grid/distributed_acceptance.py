from __future__ import annotations
import time


def distributed_acceptance_status(nodes,*,heartbeat_seconds,cpu_limit,ram_limit,disk_free_gb):
    now=time.time();online={};eligible={};reasons=[]
    for nid,n in nodes.items():
        if now-float(n.get("last_seen",0))>=float(heartbeat_seconds)*3:
            continue
        online[nid]=n
        if n.get("operator_stopped") or n.get("bootstrap_paused"):
            continue
        cpu=float(n.get("cpu_pct",100) or 100);ram=float(n.get("ram_pct",100) or 100)
        disk=float(n.get("disk_free",0) or 0)/(1024**3)
        if cpu>=float(cpu_limit) or ram>=float(ram_limit) or disk<float(disk_free_gb):
            continue
        eligible[nid]=n
    strat={nid:n for nid,n in eligible.items()
           if bool((n.get("compute_capabilities") or {}).get("strattester"))}
    archive={nid:n for nid,n in eligible.items()
             if bool((n.get("compute_capabilities") or {}).get("archive"))}
    versions=sorted({str(n.get("strattester_version") or "") for n in strat.values()
                     if str(n.get("strattester_version") or "")})
    missing_versions=sorted(nid for nid,n in strat.items()
                            if not str(n.get("strattester_version") or ""))
    if len(strat)<2:reasons.append("need at least 2 healthy Strattester nodes")
    if missing_versions:reasons.append("Strattester version missing on: "+",".join(missing_versions))
    if len(versions)>1:reasons.append("Strattester versions differ across nodes")
    if not archive:reasons.append("no healthy archive-compute node")
    return {"ready":not reasons,"online":sorted(online),"eligible":sorted(eligible),
            "strattester_nodes":sorted(strat),"archive_nodes":sorted(archive),
            "strattester_versions":versions,"missing_strattester_versions":missing_versions,
            "reasons":reasons}
