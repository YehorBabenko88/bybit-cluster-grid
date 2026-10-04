import asyncio, json, logging, time
import websockets
from .config import settings
from .resilience import backoff_delays, wait_for_internet
from .orderbook import analyze_book
from .data_quality import FeedQuality, AVAILABLE, MISSING, DEGRADED
from .continuity import SequenceGuard
from .book_velocity import BookVelocity
from .wall_tracker import WallTracker

log=logging.getLogger("microstructure")

class MicrostructureCollector:
    """Maintain causal live books, persist replayable raw batches and ML-ready snapshots."""
    def __init__(self, db, snapshot_ms=1000, wall_event_ratio=6.0, trade_tape=None, raw_capture=None):
        self.db=db
        self.snapshot_ms=int(snapshot_ms)
        self.wall_event_ratio=float(wall_event_ratio)
        self.trade_tape=trade_tape
        self.raw_capture=settings.micro_raw_capture_enabled if raw_capture is None else bool(raw_capture)

    async def run_batch(self, symbols):
        delays=backoff_delays()
        topics=[]
        for s in symbols:
            topics += [f"orderbook.50.{s}", f"tickers.{s}"]
        books={}; tickers={}; last_book_write={}; last_ticker_write={}
        quality={}; guards={}; raw_books={}
        velocity=BookVelocity(); wall_tracker=WallTracker()

        async def flush_raw(sym,event_ts):
            if not self.raw_capture:
                return
            batch=raw_books.get(sym) or []
            if not batch:
                return
            raw_books[sym]=[]
            await self.db.insert_event(sym,int(event_ts),"orderbook_raw_batch",{
                "symbol":sym,
                "events":batch,
                "event_count":len(batch),
                "first_system_ts":batch[0]["system_ts"],
                "last_system_ts":batch[-1]["system_ts"],
                "first_receive_ts":batch[0]["receive_ts"],
                "last_receive_ts":batch[-1]["receive_ts"],
            })

        while True:
            try:
                await wait_for_internet()
                async with websockets.connect(
                    settings.bybit_ws_url,
                    ping_interval=20,ping_timeout=20,max_queue=50000,close_timeout=5
                ) as ws:
                    for i in range(0,len(topics),20):
                        await ws.send(json.dumps({"op":"subscribe","args":topics[i:i+20]}))
                        await asyncio.sleep(0.05)
                    delays=backoff_delays()
                    log.info("microstructure connected",extra={"event":"ws_connected","component":"microstructure"})

                    async for raw in ws:
                        receive_ts=int(time.time()*1000)
                        msg=json.loads(raw)
                        topic=msg.get("topic","")
                        data=msg.get("data") or {}
                        system_ts=int(msg.get("ts") or receive_ts)

                        if topic.startswith("tickers."):
                            sym=topic.split(".",1)[1]
                            state=tickers.setdefault(sym,{})
                            quality.setdefault(sym,FeedQuality(sym)).mark("ticker",AVAILABLE)
                            state.update({k:v for k,v in data.items() if v is not None})
                            if system_ts-last_ticker_write.get(sym,0) >= self.snapshot_ms:
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
                                    "system_ts":system_ts,
                                    "receive_ts":receive_ts,
                                    "cross_sequence":msg.get("cs"),
                                    "raw":dict(state),
                                }
                                q=quality.setdefault(sym,FeedQuality(sym))
                                q.mark("open_interest",AVAILABLE if payload["open_interest"] is not None else MISSING,"field unavailable")
                                q.mark("funding",AVAILABLE if payload["funding_rate"] is not None else MISSING,"not supplied/applicable")
                                payload["_quality"]=q.snapshot()
                                await self.db.insert_event(sym,system_ts,"derivatives_ticker",payload)
                                last_ticker_write[sym]=system_ts

                        elif topic.startswith("orderbook."):
                            sym=topic.split(".")[-1]
                            q=quality.setdefault(sym,FeedQuality(sym))
                            state=books.setdefault(sym,{"b":{},"a":{},"u":None,"seq":None})
                            guard=guards.setdefault(sym,SequenceGuard())
                            cts=msg.get("cts",data.get("cts"))
                            is_snapshot=(msg.get("type")=="snapshot" or data.get("u")==1)

                            if self.raw_capture:
                                raw_books.setdefault(sym,[]).append({
                                    "type":"snapshot" if is_snapshot else "delta",
                                    "system_ts":system_ts,"receive_ts":receive_ts,"cts":cts,
                                    "u":data.get("u"),"seq":data.get("seq"),
                                    "b":data.get("b",[]),"a":data.get("a",[]),
                                })

                            if is_snapshot:
                                state["b"]={float(p):float(v) for p,v in data.get("b",[])}
                                state["a"]={float(p):float(v) for p,v in data.get("a",[])}
                                guard.snapshot(data.get("seq"),data.get("u"))
                                q.mark("orderbook",AVAILABLE)
                            else:
                                ok=guard.delta(data.get("seq"),data.get("u"))
                                if not ok:
                                    if guard.valid:
                                        q.mark("orderbook",DEGRADED,guard.last_reason)
                                        continue
                                    state["b"].clear(); state["a"].clear()
                                    q.mark("orderbook",MISSING,guard.last_reason or "continuity gap")
                                    await flush_raw(sym,system_ts)
                                    await self.db.insert_event(sym,system_ts,"orderbook_gap",{
                                        "reason":guard.last_reason,
                                        "last_seq":guard.last_seq,"last_update_id":guard.last_update,
                                        "received_seq":data.get("seq"),"received_update_id":data.get("u"),
                                        "cts":cts,"receive_ts":receive_ts,
                                    })
                                    raise RuntimeError(f"orderbook continuity gap for {sym}: {guard.last_reason}")
                                for p,qv in data.get("b",[]):
                                    p=float(p); qv=float(qv)
                                    if qv==0: state["b"].pop(p,None)
                                    else: state["b"][p]=qv
                                for p,qv in data.get("a",[]):
                                    p=float(p); qv=float(qv)
                                    if qv==0: state["a"].pop(p,None)
                                    else: state["a"][p]=qv

                            state["u"]=data.get("u",state["u"]); state["seq"]=data.get("seq",state["seq"])

                            if system_ts-last_book_write.get(sym,0) >= self.snapshot_ms:
                                metrics=analyze_book(list(state["b"].items()),list(state["a"].items()))
                                metrics.update(velocity.update(sym,system_ts,state["b"],state["a"]))
                                walls,removed=wall_tracker.update(sym,system_ts,metrics["walls"])
                                metrics["walls"]=walls
                                metrics["update_id"]=state["u"]; metrics["sequence"]=state["seq"]
                                metrics["cts"]=cts; metrics["system_ts"]=system_ts; metrics["receive_ts"]=receive_ts
                                metrics["book_reset"]=bool(is_snapshot)
                                metrics["_quality"]=q.snapshot()
                                await self.db.insert_event(sym,system_ts,"orderbook_snapshot",metrics)

                                tape=self.trade_tape.latest(sym) if self.trade_tape is not None else None
                                tape_fresh=bool(tape and system_ts-int(tape.get("start_ms",0)) <= max(1000,self.snapshot_ms*4))
                                ml={
                                    "t":system_ts,"known_at":receive_ts,"exchange_ts":system_ts,"cts":cts,
                                    "bid":metrics.get("best_bid") or 0.0,"ask":metrics.get("best_ask") or 0.0,
                                    "bid_depth_1":metrics.get("bid_depth_1",0.0),"ask_depth_1":metrics.get("ask_depth_1",0.0),
                                    "bid_depth_5":metrics.get("bid_depth_5",0.0),"ask_depth_5":metrics.get("ask_depth_5",0.0),
                                    "bid_depth_10":metrics.get("bid_depth_10",0.0),"ask_depth_10":metrics.get("ask_depth_10",0.0),
                                    "bid_depth_25":metrics.get("bid_depth_25",0.0),"ask_depth_25":metrics.get("ask_depth_25",0.0),
                                    "bid_depth_50":metrics.get("bid_depth_50",0.0),"ask_depth_50":metrics.get("ask_depth_50",0.0),
                                    "added_bid":metrics.get("added_bid",0.0),"removed_bid":metrics.get("removed_bid",0.0),
                                    "added_ask":metrics.get("added_ask",0.0),"removed_ask":metrics.get("removed_ask",0.0),
                                    "buy_volume":float(tape.get("buy_volume",0.0)) if tape_fresh else 0.0,
                                    "sell_volume":float(tape.get("sell_volume",0.0)) if tape_fresh else 0.0,
                                    "trade_count":int(tape.get("trade_count",0)) if tape_fresh else 0,
                                    "large_buy_volume":float(tape.get("large_buy_volume",0.0)) if tape_fresh else 0.0,
                                    "large_sell_volume":float(tape.get("large_sell_volume",0.0)) if tape_fresh else 0.0,
                                    "book_seq":state["seq"],"book_update_id":state["u"],
                                    "trade_seq_min":tape.get("first_seq") if tape_fresh else None,
                                    "trade_seq_max":tape.get("last_seq") if tape_fresh else None,
                                    "book_reset":bool(is_snapshot),"book_gap":False,
                                    "trade_gap":bool(tape.get("trade_gap",False)) if tape_fresh else False,
                                    "trade_available":bool(tape_fresh),
                                    "_quality":q.snapshot(),
                                }
                                await self.db.insert_event(sym,system_ts,"ml_microstructure_snapshot",ml)
                                await flush_raw(sym,system_ts)
                                for wall in walls:
                                    if wall["ratio"]>=self.wall_event_ratio:
                                        await self.db.insert_event(sym,system_ts,"liquidity_wall",wall)
                                for wall in removed:
                                    await self.db.insert_event(sym,system_ts,"liquidity_wall_removed",wall)
                                last_book_write[sym]=system_ts

            except asyncio.CancelledError:
                raise
            except Exception:
                d=next(delays)
                log.exception("microstructure stream failed",extra={"event":"reconnect","delay":d})
                await asyncio.sleep(d)
