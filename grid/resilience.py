import asyncio, random, logging, socket
from urllib.parse import urlsplit
log=logging.getLogger("resilience")

def _probe_tcp(host,port,timeout):
    """Open and deterministically close a short-lived reachability probe socket."""
    conn=socket.create_connection((host,port),timeout)
    try:
        return True
    finally:
        conn.close()

async def wait_for_internet(host=None,port=None):
    # Probe the configured feed dependency, not an unrelated public endpoint.
    # Validate before the retry loop: invalid configuration cannot become an endless retry.
    if host is None:
        from .config import settings
        endpoint=urlsplit(settings.bybit_rest_url)
        if endpoint.scheme not in ('http','https') or not endpoint.hostname or endpoint.username is not None or endpoint.password is not None:
            raise ValueError('invalid reachability endpoint')
        host=endpoint.hostname
        port=endpoint.port if endpoint.port is not None else (443 if endpoint.scheme=='https' else 80)
    elif port is None:
        port=443
    if type(port) is not int or not 1<=port<=65535:
        raise ValueError('invalid reachability port')
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
