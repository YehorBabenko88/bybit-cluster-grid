"""Research-only delayed paper outcomes and conservative online candidate filter.

This is an in-memory diagnostic learner, not a trained production model.
Only matured future observations update statistics; no order is executed.
"""
from __future__ import annotations
from collections import defaultdict,deque
from .book_tape_research import BookTapeResearch


class BookTapePaperLearner:
    def __init__(self,horizon_ms=60000,cost_bps=4.0,min_samples=30,
                 min_hit_rate=0.52,max_pending=1024,max_exit_delay_ms=5000):
        from math import isfinite
        if (not isinstance(horizon_ms,int) or isinstance(horizon_ms,bool) or horizon_ms<=0
            or not isfinite(float(cost_bps)) or cost_bps<0 or min_samples<1
            or not isfinite(float(min_hit_rate)) or not 0<=min_hit_rate<=1 or max_pending<1
            or not isinstance(max_exit_delay_ms,int) or isinstance(max_exit_delay_ms,bool)
            or max_exit_delay_ms<0):
            raise ValueError("invalid paper learner configuration")
        self.signal=BookTapeResearch()
        self.horizon_ms=int(horizon_ms)
        self.cost_bps=float(cost_bps)
        self.min_samples=int(min_samples)
        self.min_hit_rate=float(min_hit_rate)
        self.max_pending=int(max_pending)
        self.max_exit_delay_ms=max_exit_delay_ms
        self.pending=defaultdict(deque)
        self.stats=defaultdict(lambda:{"count":0,"wins":0,"net_bps_sum":0.0})

    def snapshot(self):
        """Versioned JSON-compatible bounded state for durable checkpoints."""
        return {"schema_version":1,"horizon_ms":self.horizon_ms,
                "cost_bps":self.cost_bps,"max_exit_delay_ms":self.max_exit_delay_ms,
                "min_samples":self.min_samples,"min_hit_rate":self.min_hit_rate,
                "max_pending":self.max_pending,"window":self.signal.window,
                "min_history":self.signal.min_history,
                "history":{sym:[list(item) for item in items]
                           for sym,items in self.signal.history.items()},
                "last_ts":dict(self.signal.last_ts),
                "pending":{sym:[dict(item) for item in items]
                           for sym,items in self.pending.items()},
                "stats":[{"symbol":sym,"pattern":pattern,"direction":direction,
                          **dict(value)}
                         for (sym,pattern,direction),value in self.stats.items() if direction in (-1,1)]}

    def restore(self,snapshot):
        """Restore only a compatible, validated snapshot, without partial mutation."""
        from collections import deque
        from math import isfinite
        if not isinstance(snapshot,dict) or snapshot.get("schema_version")!=1:
            raise ValueError("unsupported paper checkpoint")
        if (snapshot.get("horizon_ms")!=self.horizon_ms
            or snapshot.get("cost_bps")!=self.cost_bps
            or snapshot.get("max_exit_delay_ms")!=self.max_exit_delay_ms
            or snapshot.get("min_samples")!=self.min_samples
            or snapshot.get("min_hit_rate")!=self.min_hit_rate
            or snapshot.get("max_pending")!=self.max_pending
            or snapshot.get("window")!=self.signal.window
            or snapshot.get("min_history")!=self.signal.min_history):
            raise ValueError("paper checkpoint configuration mismatch")
        history=defaultdict(lambda:deque(maxlen=self.signal.window))
        last_ts={}
        pending=defaultdict(deque)
        stats=defaultdict(lambda:{"count":0,"wins":0,"net_bps_sum":0.0})
        for sym,items in snapshot["history"].items():
            if not isinstance(sym,str) or not sym or not isinstance(items,list) or len(items)>self.signal.window:
                raise ValueError("invalid paper history")
            for item in items:
                if (not isinstance(item,list) or len(item)!=4
                    or not all(isinstance(v,(int,float)) and isfinite(v) for v in item)
                    or item[0]<=0 or item[1]<=0 or item[2]<=0):
                    raise ValueError("invalid paper history item")
                history[sym].append(tuple(item))
        for sym,ts in snapshot["last_ts"].items():
            if not isinstance(sym,str) or not isinstance(ts,int) or ts<=0:
                raise ValueError("invalid paper timestamp")
            last_ts[sym]=ts
        for sym,items in snapshot["pending"].items():
            if not isinstance(sym,str) or not isinstance(items,list) or len(items)>self.max_pending:
                raise ValueError("invalid paper pending queue")
            previous_due=0
            for item in items:
                if (not isinstance(item,dict) or item.get("direction") not in (-1,1)
                    or not isinstance(item.get("pattern"),str)
                    or not isinstance(item.get("due_ms"),int)
                    or item["due_ms"]<previous_due
                    or not isinstance(item.get("entry_ts_ms"),int)
                    or item["due_ms"]-item["entry_ts_ms"]!=self.horizon_ms
                    or not isinstance(item.get("entry_price"),(int,float))
                    or not isfinite(item["entry_price"]) or item["entry_price"]<=0):
                    raise ValueError("invalid paper pending trade")
                pending[sym].append(dict(item))
                previous_due=item["due_ms"]
        for item in snapshot["stats"]:
            if (not isinstance(item,dict) or not isinstance(item.get("symbol"),str)
                or not isinstance(item.get("pattern"),str)
                or item.get("direction") not in (-1,1)
                or not isinstance(item.get("count"),int) or item["count"]<0
                or not isinstance(item.get("wins"),int) or not 0<=item["wins"]<=item["count"]
                or not isinstance(item.get("net_bps_sum"),(int,float))
                or not isfinite(item["net_bps_sum"])):
                raise ValueError("invalid paper stats")
            key=(item["symbol"],item["pattern"],item["direction"])
            if key in stats:
                raise ValueError("duplicate paper stats")
            stats[key]={"count":item["count"],"wins":item["wins"],
                        "net_bps_sum":item["net_bps_sum"]}
        self.signal.history=history
        self.signal.last_ts=last_ts
        self.pending=pending
        self.stats=stats

    def observe(self,event):
        symbol=str(event.get("symbol") or "")
        payload=event.get("payload") or {}
        result=self.signal.observe(event)
        if not result.get("eligible"):
            return result
        ts=int(result["ts_ms"])
        price=float(payload["close"])
        settled=[];expired=[]
        queue=self.pending[symbol]
        # All labels use a later received event, never a future bar during entry.
        while queue and ts>=queue[0]["due_ms"]:
            trade=queue.popleft()
            # A market-data outage must not be mistaken for a fill exactly at
            # the requested horizon; discard labels with excessive exit delay.
            if ts-trade["due_ms"]>self.max_exit_delay_ms:
                expired.append({"pattern":trade["pattern"],
                                "entry_ts_ms":trade["entry_ts_ms"],
                                "due_ms":trade["due_ms"],"observed_ts_ms":ts,
                                "reason":"stale_exit_price"})
                continue
            net=(price/trade["entry_price"]-1)*10000*trade["direction"]-self.cost_bps
            stat=self.stats[(symbol,trade["pattern"],trade["direction"])]
            stat["count"]+=1
            stat["wins"]+=int(net>0)
            stat["net_bps_sum"]+=net
            settled.append({"pattern":trade["pattern"],"entry_ts_ms":trade["entry_ts_ms"],
                            "exit_ts_ms":ts,"net_bps":round(net,6),
                            "direction":trade["direction"]})
        direction=int(result["direction"])
        pattern="jbe" if result["patterns"]["jbe_proxy"] else "dbi" if result["patterns"]["dbi_proxy"] else "trend"
        stat=self.stats[(symbol,pattern,direction)]
        hit_rate=stat["wins"]/stat["count"] if stat["count"] else None
        mean_net=stat["net_bps_sum"]/stat["count"] if stat["count"] else None
        blocked=(stat["count"]>=self.min_samples
                 and (hit_rate<self.min_hit_rate or mean_net<=0))
        result["paper"]={"matured":settled,"expired":expired,"pattern":pattern,
                         "historical_count":stat["count"],"historical_hit_rate":hit_rate,
                         "historical_mean_net_bps":round(mean_net,6) if mean_net is not None else None,
                         "cost_bps":self.cost_bps,"horizon_ms":self.horizon_ms,
                         "pending":len(queue),"blocked_by_past_evidence":blocked}
        if direction and blocked:
            result["direction"]=0
            result["decision"]="ABSTAIN_NEGATIVE_PAPER_EVIDENCE"
        elif direction and len(queue)>=self.max_pending:
            result["direction"]=0
            result["decision"]="ABSTAIN_PAPER_BACKLOG"
        elif direction:
            queue.append({"due_ms":ts+self.horizon_ms,"entry_ts_ms":ts,
                          "entry_price":price,"direction":direction,"pattern":pattern})
            result["paper"]["pending"]=len(queue)
        return result
