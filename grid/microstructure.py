import asyncio, json, logging, time
from collections import deque
import websockets
from .config import settings
from .resilience import backoff_delays, wait_for_internet
from .orderbook import analyze_book, parse_book_levels
from .data_quality import FeedQuality, safe_float, AVAILABLE, MISSING
from .continuity import SequenceGuard
from .book_velocity import BookVelocity
from .wall_tracker import WallTracker
from .topic_watchdog import TopicWatchdog

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
        subscribed_topics=set(topics)
        books={}
        tickers={}
        last_book_write={}
        last_ticker_write={}
        last_ticker_seen={}
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
            last_ticker_seen.clear()
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
                    pending_market_frames=deque()
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
                            if not isinstance(ack,dict):
                                raise RuntimeError("invalid Bybit subscription response")
                            if ack.get("op")=="subscribe":
                                args=(ack.get("data") or {}).get("args") if isinstance(ack.get("data"),dict) else None
                                if args is None:
                                    args=ack.get("args")
                                if args is not None and not set(batch_topics).issubset(set(args)):
                                    continue
                                if ack.get("success") is not True:
                                    raise RuntimeError("Bybit subscription rejected: "+str(ack.get("ret_msg") or ack))
                                break
                            # Earlier subscription batches can emit snapshots before
                            # later batches acknowledge. Preserve those frames in order.
                            if isinstance(ack,dict) and isinstance(ack.get("topic"),str):
                                if ack["topic"].startswith(("orderbook.","tickers.")):
                                    if len(pending_market_frames)>=2000:
                                        raise RuntimeError("subscription market frame buffer overflow")
                                    pending_market_frames.append(raw)
                        await asyncio.sleep(0.05)
                    delays=backoff_delays()
                    log.info("microstructure connected",extra={"event":"ws_connected","component":"microstructure"})
                    # A live socket can still have a silently stalled book topic.
                    # Use monotonic receipt time rather than exchange timestamps.
                    book_watchdog=TopicWatchdog(symbols,asyncio.get_running_loop().time(),timeout_seconds=120.0)

                    while True:
                        if pending_market_frames:
                            raw=pending_market_frames.popleft()
                        else:
                            try:
                                raw=await asyncio.wait_for(ws.recv(),timeout=10)
                            except asyncio.TimeoutError:
                                raw=None
                        now=asyncio.get_running_loop().time()
                        stalled=book_watchdog.stalled(now)
                        if stalled:
                            raise RuntimeError("stalled orderbook topics: "+",".join(stalled[:10]))
                        if raw is None:
                            continue
                        msg=json.loads(raw)
                        if not isinstance(msg,dict):
                            log.warning("non-object market frame ignored",extra={"event":"invalid_market_frame"})
                            continue
                        topic=msg.get("topic","")
                        data=msg.get("data") or {}
                        if not isinstance(topic,str) or not isinstance(data,dict):
                            log.warning("invalid market envelope ignored",extra={"event":"invalid_market_envelope"})
                            continue
                        try:
                            ts=int(msg.get("ts") or time.time()*1000)
                        except (ValueError,TypeError,OverflowError):
                            log.warning("invalid market timestamp ignored",extra={"event":"invalid_market_timestamp"})
                            continue

                        if topic.startswith(("tickers.","orderbook.")) and topic not in subscribed_topics:
                            log.warning("unsubscribed market topic ignored",extra={"event":"unknown_market_topic"})
                            continue

                        if topic.startswith("tickers."):
                            sym=topic.split(".",1)[1]
                            if ts<last_ticker_seen.get(sym,-1):
                                log.warning("stale ticker ignored",extra={"event":"ticker_stale","component":sym})
                                continue
                            last_ticker_seen[sym]=ts
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
                            try:
                                bids=parse_book_levels(data.get("b"),snapshot=is_snapshot)
                                asks=parse_book_levels(data.get("a"),snapshot=is_snapshot)
                            except (ValueError,TypeError):
                                guard.valid=False
                                velocity.state.pop(sym,None)
                                wall_tracker.state.pop(sym,None)
                                state["b"].clear(); state["a"].clear()
                                q.mark("orderbook",MISSING,"malformed orderbook levels")
                                log.warning("malformed orderbook levels",extra={"event":"orderbook_bad_levels","component":sym})
                                continue
                            if is_snapshot:
                                if not guard.valid:
                                    velocity.state.pop(sym,None)
                                    wall_tracker.state.pop(sym,None)
                                was_valid=guard.valid
                                if not guard.snapshot(data.get("seq"),data.get("u")):
                                    if was_valid and guard.valid:
                                        # Stale replay: retain the newer, valid book.
                                        log.warning("stale orderbook snapshot ignored",extra={"event":"orderbook_stale_snapshot","component":sym})
                                        continue
                                    state["b"].clear(); state["a"].clear()
                                    q.mark("orderbook",MISSING,"snapshot missing sequence metadata")
                                    log.warning("orderbook snapshot missing sequence metadata",extra={"event":"orderbook_bad_snapshot","component":sym})
                                    continue
                                state["b"]=bids
                                state["a"]=asks
                                q.mark("orderbook",AVAILABLE)
                            elif not guard.delta(data.get("seq"),data.get("u")):
                                velocity.state.pop(sym,None)
                                wall_tracker.state.pop(sym,None)
                                state["b"].clear(); state["a"].clear()
                                q.mark("orderbook",MISSING,"sequence gap; waiting for fresh snapshot")
                                log.warning("orderbook sequence gap",extra={"event":"orderbook_gap","component":sym})
                                continue
                            else:
                                for p,qty in bids.items():
                                    if qty==0: state["b"].pop(p,None)
                                    else: state["b"][p]=qty
                                for p,qty in asks.items():
                                    if qty==0: state["a"].pop(p,None)
                                    else: state["a"][p]=qty
                            # Depth-50 streams should never accumulate unbounded levels.
                            # A malformed sequence must recover from a fresh snapshot.
                            if len(state["b"])>200 or len(state["a"])>200:
                                guard.valid=False
                                velocity.state.pop(sym,None)
                                wall_tracker.state.pop(sym,None)
                                state["b"].clear(); state["a"].clear()
                                q.mark("orderbook",MISSING,"accumulated level limit exceeded")
                                log.warning("orderbook level limit exceeded",extra={"event":"orderbook_level_overflow","component":sym})
                                continue
                            book_watchdog.observe(sym,now)
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
