import asyncio, random, logging, socket
log=logging.getLogger("resilience")

async def wait_for_internet(host="api.bybit.com",port=443):
    delay=1
    while True:
        try:
            await asyncio.to_thread(socket.create_connection,(host,port),3)
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
