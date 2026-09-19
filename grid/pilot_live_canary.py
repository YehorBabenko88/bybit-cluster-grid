def live_canary_health(heartbeats,min_healthy=5):
    if len(heartbeats)<int(min_healthy):
        return {"healthy":False,"reason":"not_enough_heartbeats","count":len(heartbeats)}
    recent=heartbeats[-int(min_healthy):]
    for h in recent:
        if not h.get("integrity_ok",False):return {"healthy":False,"reason":"integrity"}
        if h.get("pressure_state") not in (None,"NORMAL","SOFT_PRESSURE"):
            return {"healthy":False,"reason":"pressure"}
        if float(h.get("db_write_failures",0) or 0)>0:return {"healthy":False,"reason":"db_write_failure"}
        if float(h.get("db_queue_ratio",0) or 0)>=.8:return {"healthy":False,"reason":"db_queue"}
        if int(h.get("wanted_symbols",0) or 0)<1 or int(h.get("active_trade_streams",0) or 0)<1:
            return {"healthy":False,"reason":"no_live_symbols"}
    return {"healthy":True,"reason":None,"count":len(recent)}
