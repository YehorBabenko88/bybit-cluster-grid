import asyncio, json, logging, time
import websockets
from .config import settings
from .resilience import backoff_delays, wait_for_internet
from .orderbook import analyze_book
from .data_quality import FeedQuality, safe_float, AVAILABLE, MISSING

log=logging.getLogger("microstructure")

class MicrostructureCollector:
    """
    Maintains order books in memory from snapshot+delta messages.
    Writes throttled analytical snapshots instead of every 20ms delta.
    Ticker/OI fields are merged because Bybit ticker deltas omit unchanged fields.
    """
    def __init__(self, db, snapshot_ms=1000, wall_event_ratio=6.0):
        self.db=db
        self.snapshot_ms=snapshot_ms
        self.wall_event_ratio=wall_event_ratio

    async def run_batch(self, symbols):
        delays=backoff_delays()
        topics=[]
        for s in symbols:
            topics += [f"orderbook.50.{s}", f"tickers.{s}"]
        books={}
        tickers={}
        last_book_write={}
        last_ticker_write={}

        while True:
            try:
                await wait_for_internet()
                async with websockets.connect(
                    settings.bybit_ws_url,
                    ping_interval=20, ping_timeout=20,
                    max_queue=50000, close_timeout=5
                ) as ws:
                    # Small subscription batches reduce rejection risk and make reconnect gentler.
                    for i in range(0,len(topics),20):
                        await ws.send(json.dumps({"op":"subscribe","args":topics[i:i+20]}))
                        await asyncio.sleep(0.05)
                    delays=backoff_delays()
                    log.info("microstructure connected",extra={"event":"ws_connected","component":"microstructure"})

                    async for raw in ws:
                        msg=json.loads(raw)
                        topic=msg.get("topic","")
                        data=msg.get("data") or {}
                        ts=int(msg.get("ts") or time.time()*1000)

                        if topic.startswith("tickers."):
                            sym=topic.split(".",1)[1]
                            state=tickers.setdefault(sym,{})
                            quality.setdefault(sym,FeedQuality(sym)).mark("ticker",AVAILABLE)
                            state.update({k:v for k,v in data.items() if v is not None})
                            if ts-last_ticker_write.get(sym,0) >= self.snapshot_ms:
                                payload={
                                    "open_interest":state.get("openInterest"),
                                    "open_interest_value":state.get("openInterestValue"),
                                    "funding_rate":state.get("fundingRate"),
                                    "funding_interval_hour":state.get("fundingIntervalHour"),
                                    "next_funding_time":state.get("nextFundingTime"),
                                    "mark_price":state.get("markPrice"),
                                    "index_price":state.get("indexPrice"),
                                    "last_price":state.get("lastPrice"),
                                    "basis_rate":state.get("basisRate"),
                                    "bid1_price":state.get("bid1Price"),
                                    "bid1_size":state.get("bid1Size"),
                                    "ask1_price":state.get("ask1Price"),
                                    "ask1_size":state.get("ask1Size"),
                                    "volume24h":state.get("volume24h"),
                                    "turnover24h":state.get("turnover24h"),
                                }
                                q=quality.setdefault(sym,FeedQuality(sym))
                                q.mark("open_interest", AVAILABLE if payload["open_interest"] is not None else MISSING, "field unavailable")
                                q.mark("funding", AVAILABLE if payload["funding_rate"] is not None else MISSING, "not supplied/applicable")
                                payload["_quality"]=q.snapshot()
                                await self.db.insert_event(sym,ts,"derivatives_ticker",payload)
                                last_ticker_write[sym]=ts

                        elif topic.startswith("orderbook."):
                            sym=topic.split(".")[-1]
                            state=books.setdefault(sym,{"b":{},"a":{},"u":None,"seq":None})
                            q=quality.setdefault(sym,FeedQuality(sym))
                            # A fresh snapshot must replace the local book.
                            if msg.get("type")=="snapshot" or data.get("u")==1:
                                state["b"]={float(p):float(q) for p,q in data.get("b",[])}
                                state["a"]={float(p):float(q) for p,q in data.get("a",[])}
                            else:
                                for p,q in data.get("b",[]):
                                    p=float(p); q=float(q)
                                    if q==0: state["b"].pop(p,None)
                                    else: state["b"][p]=q
                                for p,q in data.get("a",[]):
                                    p=float(p); q=float(q)
                                    if q==0: state["a"].pop(p,None)
                                    else: state["a"][p]=q
                            state["u"]=data.get("u",state["u"])
                            state["seq"]=data.get("seq",state["seq"])

                            if ts-last_book_write.get(sym,0) >= self.snapshot_ms:
                                metrics=analyze_book(list(state["b"].items()),list(state["a"].items()))
                                metrics["update_id"]=state["u"]
                                metrics["sequence"]=state["seq"]
                                metrics["cts"]=data.get("cts")
                                metrics["_quality"]=q.snapshot()
                                await self.db.insert_event(sym,ts,"orderbook_snapshot",metrics)
                                for wall in metrics["walls"]:
                                    if wall["ratio"] >= self.wall_event_ratio:
                                        await self.db.insert_event(sym,ts,"liquidity_wall",wall)
                                last_book_write[sym]=ts

            except asyncio.CancelledError:
                raise
            except Exception:
                d=next(delays)
                log.exception("microstructure stream failed",extra={"event":"reconnect","delay":d})
                await asyncio.sleep(d)
