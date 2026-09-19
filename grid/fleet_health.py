import time

async def fleet_health(pool,nodes,heartbeat_seconds):
    now=time.time(); online=[];offline=[];integrity=[];pressure=[];queues=[]
    for nid,n in sorted(nodes.items()):
        (online if now-float(n.get("last_seen",0))<heartbeat_seconds*3 else offline).append(nid)
        if not n.get("integrity_ok",True):integrity.append(nid)
        if n.get("pressure_state") not in (None,"NORMAL"):pressure.append(f"{nid}:{n.get('pressure_state')}")
        qr=float(n.get("db_queue_ratio",0) or 0);sr=float(n.get("db_spool_ratio",0) or 0)
        if max(qr,sr)>=.5:queues.append(f"{nid}:{max(qr,sr):.0%}")
    leader=await pool.fetchrow("SELECT owner,lease_until FROM service_leases WHERE service_key='control-plane-leader'")
    repairs=await pool.fetch("""SELECT node_id,status,target_version,last_error FROM integrity_repairs
      WHERE status NOT IN ('healthy') ORDER BY created_at DESC LIMIT 10""")
    return {"online":online,"offline":offline,"integrity":integrity,"pressure":pressure,"queues":queues,
            "leader":dict(leader) if leader else None,"repairs":[dict(x) for x in repairs]}
