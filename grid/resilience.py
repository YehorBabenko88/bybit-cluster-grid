import asyncio, random, logging, socket
log=logging.getLogger("resilience")

def _probe_tcp(host,port,timeout):
    """Open and deterministically close a short-lived reachability probe socket."""
    conn=socket.create_connection((host,port),timeout)
    try:
        return True
    finally:
        conn.close()

async def wait_for_internet(host="api.bybit.com",port=443):
    delay=1
    while True:
        try:
            await asyncio.to_thread(_probe_tcp,host,port,3)
            return
        except Exception:
            log.warning("internet unavailable",extra={"event":"internet_down","delay":delay})
            await asyncio.sleep(delay+random.random())
            delay=min(60,delay*2)

def backoff_delays(start=1,cap=60):
    d=start
    while True:
        yield d+random.uniform(0,d*0.2)
        d=min(cap,d*2)
