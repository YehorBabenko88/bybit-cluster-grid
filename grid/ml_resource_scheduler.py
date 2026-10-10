import math
from dataclasses import dataclass

@dataclass(frozen=True)
class Workload:
    kind:str
    cpu:float=1.0
    ram_gb:float=1.0
    scratch_gb:float=1.0
    input_gb:float=0.0
    gpu:bool=False
    data_locality:str|None=None

def rank_nodes(nodes,workload:Workload):
    """Rank execution nodes by measured headroom minus estimated LAN transfer cost."""
    # Job payloads may be user-controlled: reject negative/NaN/infinite
    # estimates before placement or reservation arithmetic.
    estimates=(workload.cpu,workload.ram_gb,workload.scratch_gb,workload.input_gb)
    if any(not math.isfinite(float(v)) or float(v)<0 for v in estimates):
        return []
    ranked=[]
    for node_id,n in nodes.items():
        if (n.get("pressure_state") or "NORMAL") in ("REDUCE_LOAD","CRITICAL"): continue
        # New heavy ML work is admitted only on a disk-normal node. Existing
        # leased work is handled by lease/cancellation semantics, not stolen here.
        if (n.get("disk_pressure_state") or "NORMAL")!="NORMAL": continue
        try:
            cpu_pct=float(n.get("cpu_pct",100))
            ram_bytes=float(n.get("ram_available",0))
            disk_bytes=float(n.get("disk_free",0))
            cores=int(n.get("cpu_count",1))
            lan_mbps=float(n.get("lan_mbps",100))
        except (TypeError,ValueError,OverflowError):
            continue
        if (not all(math.isfinite(v) for v in (cpu_pct,ram_bytes,disk_bytes,lan_mbps))
                or cpu_pct<0 or cpu_pct>100 or ram_bytes<0 or disk_bytes<0
                or cores<=0 or lan_mbps<=0):
            continue
        cpu_free=max(0.0,100-cpu_pct)
        ram_free=ram_bytes/1024**3
        disk_free=disk_bytes/1024**3
        required_cpu_pct=100.0*workload.cpu/cores
        if cpu_free<max(15.0,required_cpu_pct) or ram_free<workload.ram_gb*1.25 or disk_free<workload.scratch_gb*1.25: continue
        if workload.gpu and not n.get("gpu_available",False): continue
        locality=1.0 if workload.data_locality and n.get("data_location")==workload.data_locality else 0.0
        lan_mbps=max(1.0,lan_mbps)
        transfer_seconds=(workload.input_gb*8*1024)/lan_mbps if workload.input_gb and not locality else 0.0
        compute=(cpu_free/100)*max(1,int(n.get("cpu_count",1)))*2 + min(ram_free/8,4)
        score=compute + 5*locality - min(20,transfer_seconds/60)
        ranked.append((score,node_id,{"transfer_seconds":transfer_seconds,"locality":locality}))
    return sorted(ranked,reverse=True)

def choose_node(nodes,workload):
    ranked=rank_nodes(nodes,workload)
    return ranked[0] if ranked else None
