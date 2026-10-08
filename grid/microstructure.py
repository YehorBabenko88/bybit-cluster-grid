import asyncio, json, logging, time
import websockets
from .config import settings
from .resilience import backoff_delays, wait_for_internet
from .orderbook import analyze_book
from .data_quality import FeedQuality, safe_float, AVAILABLE, MISSING
from .continuity import SequenceGuard
from .book_velocity import BookVelocity
from .wall_tracker import WallTracker

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
        quality={}
        guards={}
        velocity=BookVelocity()
        wall_tracker=WallTracker()

        while True:
            # A new socket starts a new market-data epoch. Never reuse orderbook
            # sequence guards, ticker deltas, or derived velocity across reconnects.
            books.clear()
            tickers.clear()
            last_book_write.clear()
            last_ticker_write.clear()
            quality.clear()
            guards.clear()
            velocity=BookVelocity()
            wall_tracker=WallTracker()
            try:
                await wait_for_internet()
                async with websockets.connect(
                    settings.bybit_ws_url,
                    ping_interval=20, ping_timeout=20,
                    max_queue=2000, close_timeout=5
                ) as ws:
                    # Small subscription batches reduce rejection risk and make reconnect gentler.
                    # Every request must be acknowledged; otherwise a transport can stay
                    # healthy while the market subscription itself was rejected.
                    for i in range(0,len(topics),20):
                        batch_topics=topics[i:i+20]
                        await ws.send(json.dumps({"op":"subscribe","args":batch_topics}))
                        ack_deadline=asyncio.get_running_loop().time()+15
                        while True:
                            remaining=ack_deadline-asyncio.get_running_loop().time()
                            if remaining<=0:
                                raise asyncio.TimeoutError("Bybit microstructure subscription ACK timeout")
                            raw=await asyncio.wait_for(ws.recv(),timeout=remaining)
                            ack=json.loads(raw)
                            if ack.get("op")=="subscribe":
                                args=(ack.get("data") or {}).get("args") if isinstance(ack.get("data"),dict) else None
                                if args is None:
                                    args=ack.get("args")
                                if args is not None and not set(batch_topics).issubset(set(args)):
                                    continue
                                if ack.get("success") is not True:
                                    raise RuntimeError("Bybit subscription rejected: "+str(ack.get("ret_msg") or ack))
                                break
                            # Ignore connection-level control frames before ACK. Market
                            # data is not expected before subscription acknowledgement.
                        await asyncio.sleep(0.05)
                    delays=backoff_delays()
                    log.info("microstructure connected",extra={"event":"ws_connected","component":"microstructure"})

                    while True:
                        raw=await asyncio.wait_for(ws.recv(),timeout=45)
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
                            guard=guards.setdefault(sym,SequenceGuard())
                            is_snapshot=msg.get("type")=="snapshot" or data.get("u")==1
                            if is_snapshot:
                                if not guard.valid:
                                    # A fresh book epoch cannot inherit prior wall
                                    # lifetimes or rate-of-change baselines.
                                    velocity.state.pop(sym,None)
                                    wall_tracker.state.pop(sym,None)
                                state["b"]={float(p):float(q) for p,q in data.get("b",[])}
                                state["a"]={float(p):float(q) for p,q in data.get("a",[])}
                                guard.snapshot(data.get("seq"),data.get("u"))
                                q.mark("orderbook",AVAILABLE)
                            elif not guard.delta(data.get("seq"),data.get("u")):
                                velocity.state.pop(sym,None)
                                wall_tracker.state.pop(sym,None)
                                state["b"].clear(); state["a"].clear()
                                q.mark("orderbook",MISSING,"sequence gap; waiting for fresh snapshot")
                                log.warning("orderbook sequence gap",extra={"event":"orderbook_gap","component":sym})
                                continue
                            else:
                                for p,qv in data.get("b",[]):
                                    p=float(p); qv=float(qv)
                                    if qv==0: state["b"].pop(p,None)
                                    else: state["b"][p]=qv
                                for p,qv in data.get("a",[]):
                                    p=float(p); qv=float(qv)
                                    if qv==0: state["a"].pop(p,None)
                                    else: state["a"][p]=qv
                            state["u"]=data.get("u",state["u"])
                            state["seq"]=data.get("seq",state["seq"])

                            if ts-last_book_write.get(sym,0) >= self.snapshot_ms:
                                metrics=analyze_book(list(state["b"].items()),list(state["a"].items()))
                                metrics.update(velocity.update(sym,ts,state["b"],state["a"]))
                                walls,removed=wall_tracker.update(sym,ts,metrics["walls"])
                                metrics["walls"]=walls
                                metrics["update_id"]=state["u"]
                                metrics["sequence"]=state["seq"]
                                metrics["cts"]=data.get("cts")
                                metrics["_quality"]=q.snapshot()
                                await self.db.insert_event(sym,ts,"orderbook_snapshot",metrics)
                                for wall in walls:
                                    if wall["ratio"] >= self.wall_event_ratio:
                                        await self.db.insert_event(sym,ts,"liquidity_wall",wall)
                                for wall in removed:
                                    await self.db.insert_event(sym,ts,"liquidity_wall_removed",wall)
                                last_book_write[sym]=ts

            except asyncio.CancelledError:
                raise
            except Exception:
                d=next(delays)
                log.exception("microstructure stream failed",extra={"event":"reconnect","delay":d})
                await asyncio.sleep(d)
