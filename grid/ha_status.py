async def ha_status(pool,nodes,heartbeat_seconds):
    alive=[n for n,v in nodes.items() if __import__("time").time()-float(v.get("last_seen",0))<heartbeat_seconds*3]
    try:
        lease=await pool.fetchrow("""SELECT owner,lease_until,heartbeat_at FROM service_leases
          WHERE service_key='control-plane-leader'""")
        db_ok=True
    except Exception:
        lease=None;db_ok=False
    return {
      "data_plane_redundant":len(alive)>1,
      "control_candidates":len(alive),
      "db_reachable":db_ok,
      "leader_owner":lease["owner"] if lease else None,
      "automatic_db_failover":False,
      "ha_level":"DATA_PLANE_ONLY" if len(alive)>1 else "SINGLE_NODE",
      "limitation":"automatic PostgreSQL primary failover is intentionally disabled until replicated DB fencing is configured"
    }
