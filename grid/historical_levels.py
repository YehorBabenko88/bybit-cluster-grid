from dataclasses import dataclass,field
from collections import deque

APPROACH="APPROACH"
FIRST_CROSS="FIRST_CROSS"
FALSE_BREAK="FALSE_BREAK"
REJECTION="REJECTION"
ACCEPTED_BREAK="ACCEPTED_BREAK"
RETEST_HOLD="RETEST_HOLD"

@dataclass
class Level:
    timeframe:str
    kind:str
    source_ts:object
    price:float
    side:str
    crossed:bool=False
    cross_ts:object=None
    tests:int=0
    accepted:bool=False
    pre_features:dict=field(default_factory=dict)
    post_bars:int=0

class HistoricalLevelTracker:
    """Event labels around HTF levels, preserving features known before first cross."""
    def __init__(self,approach_pct=.002,break_buffer_pct=.0002,accept_bars=2,false_break_bars=3):
        self.approach_pct=float(approach_pct); self.break_buffer_pct=float(break_buffer_pct)
        self.accept_bars=int(accept_bars); self.false_break_bars=int(false_break_bars)
        self.levels={}; self.prev_close={}; self.after={}

    def register(self,symbol,timeframe,kind,source_ts,price,side):
        key=(timeframe,kind,source_ts)
        self.levels.setdefault(symbol,{})[key]=Level(timeframe,kind,source_ts,float(price),side)
        return self.levels[symbol][key]

    def observe(self,symbol,ts,o,h,l,c,features):
        o,h,l,c=map(float,(o,h,l,c)); prev=self.prev_close.get(symbol,c); events=[]
        for key,x in self.levels.get(symbol,{}).items():
            p=x.price; buf=max(abs(p)*self.break_buffer_pct,1e-18)
            dist=abs(c-p)/max(abs(p),1e-18)
            if not x.crossed and dist<=self.approach_pct:
                x.pre_features=dict(features)
                events.append((APPROACH,x,{"distance_pct":dist}))
            up=prev<=p and c>p+buf
            down=prev>=p and c<p-buf
            if not x.crossed and (up or down):
                x.crossed=True; x.cross_ts=ts; x.tests+=1; x.post_bars=0
                direction="UP" if up else "DOWN"
                self.after[(symbol,key)]={"direction":direction,"bars":0,"accept":0,"returned":False}
                events.append((FIRST_CROSS,x,{"direction":direction,"pre_features":dict(x.pre_features),"event_features":dict(features)}))
                continue
            state=self.after.get((symbol,key))
            if not state: continue
            state["bars"]+=1; x.post_bars=state["bars"]
            broken_side=(state["direction"]=="UP" and c>p+buf) or (state["direction"]=="DOWN" and c<p-buf)
            back_inside=(state["direction"]=="UP" and c<p-buf) or (state["direction"]=="DOWN" and c>p+buf)
            if broken_side: state["accept"]+=1
            else: state["accept"]=0
            if not x.accepted and state["accept"]>=self.accept_bars:
                x.accepted=True
                events.append((ACCEPTED_BREAK,x,{"direction":state["direction"],"bars_to_accept":state["bars"]}))
            if back_inside and state["bars"]<=self.false_break_bars:
                events.append((FALSE_BREAK,x,{"direction":state["direction"],"bars_after_cross":state["bars"]}))
                self.after.pop((symbol,key),None); continue
            # Retest after accepted break: candle touches level but closes on broken side.
            touches=l-buf<=p<=h+buf
            if x.accepted and touches and broken_side:
                events.append((RETEST_HOLD,x,{"direction":state["direction"],"bars_after_cross":state["bars"]}))
                self.after.pop((symbol,key),None)
            elif not x.accepted and touches and not x.crossed:
                events.append((REJECTION,x,{"distance_pct":dist}))
        self.prev_close[symbol]=c
        return events
