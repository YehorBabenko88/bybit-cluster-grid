import asyncio, json, logging, time
import websockets
from .config import settings
from .resilience import backoff_delays,wait_for_internet
from .orderbook import analyze_book
log=logging.getLogger("microstructure")

class MicrostructureCollector:
    def __init__(self,symbols,db):
        self.symbols=symbols; self.db=db

    async def run_batch(self,symbols):
        delays=backoff_delays()
        topics=[]
        for s in symbols:
            topics += [f"orderbook.50.{s}",f"tickers.{s}"]
        while True:
            try:
                await wait_for_internet()
                async with websockets.connect(settings.bybit_ws_url,ping_interval=20,ping_timeout=20,max_queue=20000) as ws:
                    await ws.send(json.dumps({"op":"subscribe","args":topics}))
                    delays=backoff_delays()
                    books={}
                    async for raw in ws:
                        msg=json.loads(raw); topic=msg.get("topic",""); data=msg.get("data",{})
                        ts=int(msg.get("ts") or time.time()*1000)
                        if topic.startswith("tickers."):
                            sym=topic.split(".",1)[1]
                            payload={
                                "open_interest":data.get("openInterest"),
                                "funding_rate":data.get("fundingRate"),
                                "mark_price":data.get("markPrice"),
                                "index_price":data.get("indexPrice"),
                                "basis":data.get("basis"),
                            }
                            await self.db.insert_event(sym,ts,"ticker",payload)
                        elif topic.startswith("orderbook."):
                            sym=topic.split(".")[-1]
                            state=books.setdefault(sym,{"b":{},"a":{}})
                            if msg.get("type")=="snapshot":
                                state["b"]={float(p):float(q) for p,q in data.get("b",[])}
                                state["a"]={float(p):float(q) for p,q in data.get("a",[])}
                            else:
                                for p,q in data.get("b",[]):
                                    p=float(p); q=float(q)
                                    state["b"].pop(p,None) if q==0 else state["b"].__setitem__(p,q)
                                for p,q in data.get("a",[]):
                                    p=float(p); q=float(q)
                                    state["a"].pop(p,None) if q==0 else state["a"].__setitem__(p,q)
                            metrics=analyze_book(list(state["b"].items()),list(state["a"].items()))
                            await self.db.insert_event(sym,ts,"orderbook_metrics",metrics)
            except asyncio.CancelledError: raise
            except Exception:
                d=next(delays)
                log.exception("microstructure stream failed",extra={"event":"reconnect","delay":d})
                await asyncio.sleep(d)
