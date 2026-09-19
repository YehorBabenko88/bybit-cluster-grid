import asyncio,json,time
import aiohttp, websockets
from .config import settings
from .resources import snapshot
from .models import Trade
from .cluster import FootprintBuilder
from .storage import Storage
from .bybit import linear_symbols

class Worker:
    def __init__(self):
        self.wanted=set(); self.tasks={}; self.storage=Storage(); self.meta={}
    async def heartbeat(self):
        async with aiohttp.ClientSession() as s:
            while True:
                snap=snapshot()
                try:
                    async with s.post(settings.coordinator_url+"/heartbeat",json=snap,
                        headers={"X-Grid-Token":settings.grid_shared_token},timeout=10) as r:
                        if r.status==200: self.wanted=set((await r.json())["symbols"])
                    await self.reconcile()
                except Exception as e: print("heartbeat",repr(e),flush=True)
                await asyncio.sleep(settings.heartbeat_seconds)
    async def reconcile(self):
        for sym in list(self.tasks):
            if sym not in self.wanted: self.tasks.pop(sym).cancel()
        for sym in self.wanted:
            if sym not in self.tasks:
                self.tasks[sym]=asyncio.create_task(self.stream(sym))
    async def stream(self,symbol):
        tick=self.meta[symbol]["tick_size"]; fp=FootprintBuilder(tick,settings.cluster_interval_seconds)
        backoff=1
        while True:
            try:
                async with websockets.connect(settings.bybit_ws_url,ping_interval=20,ping_timeout=20,max_queue=10000) as ws:
                    await ws.send(json.dumps({"op":"subscribe","args":[f"publicTrade.{symbol}"]}))
                    backoff=1
                    while True:
                        msg=json.loads(await ws.recv())
                        for x in msg.get("data",[]):
                            fp.add(Trade(symbol,int(x["T"]),float(x["p"]),float(x["v"]),x["S"],x.get("i","")))
                        for row in fp.pop_closed(int(time.time()*1000)): await self.storage.save(row)
            except asyncio.CancelledError: raise
            except Exception as e:
                print(symbol,"stream error",repr(e),flush=True); await asyncio.sleep(backoff); backoff=min(30,backoff*2)
    async def run(self):
        await self.storage.start()
        self.meta={x["symbol"]:x for x in await linear_symbols(settings.bybit_rest_url)}
        await self.heartbeat()

async def main(): await Worker().run()
if __name__=="__main__": asyncio.run(main())
