from dataclasses import dataclass
from datetime import datetime,timedelta,timezone

TIMEFRAMES=("1H","4H","1D","1W","1M","1Y")

@dataclass(frozen=True)
class GeneratedLevel:
    symbol:str
    timeframe:str
    kind:str
    source_ts:datetime
    price:float
    available_ts:datetime

class HistoricalLevelGenerator:
    """Aggregates 1m bars into completed HTF periods without look-ahead."""
    def __init__(self,timeframes=TIMEFRAMES):
        self.timeframes=tuple(timeframes)
        self.current={}

    def on_candle(self,row):
        symbol=row["symbol"]; ts=_utc(row["ts"]); emitted=[]
        for tf in self.timeframes:
            start,end=_period(ts,tf)
            key=(symbol,tf)
            cur=self.current.get(key)
            if cur is None:
                self.current[key]=_new(start,end,row)
                continue
            if start!=cur["start"]:
                emitted.extend(_levels(symbol,tf,cur))
                self.current[key]=_new(start,end,row)
            else:
                cur["high"]=max(cur["high"],float(row["high"]))
                cur["low"]=min(cur["low"],float(row["low"]))
                cur["close"]=float(row["close"])
        return emitted

def _new(start,end,row):
    return {"start":start,"end":end,"high":float(row["high"]),"low":float(row["low"]),
            "open":float(row["open"]),"close":float(row["close"])}

def _levels(symbol,tf,b):
    # available_ts is period end: strategies may not use the level before then.
    return [GeneratedLevel(symbol,tf,"HIGH",b["start"],b["high"],b["end"]),
            GeneratedLevel(symbol,tf,"LOW",b["start"],b["low"],b["end"])]

def _utc(ts):
    if ts.tzinfo is None: return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)

def _period(ts,tf):
    if tf=="1H":
        s=ts.replace(minute=0,second=0,microsecond=0); return s,s+timedelta(hours=1)
    if tf=="4H":
        s=ts.replace(hour=(ts.hour//4)*4,minute=0,second=0,microsecond=0); return s,s+timedelta(hours=4)
    if tf=="1D":
        s=ts.replace(hour=0,minute=0,second=0,microsecond=0); return s,s+timedelta(days=1)
    if tf=="1W":
        d=(ts-timedelta(days=ts.weekday())).date()
        s=datetime(d.year,d.month,d.day,tzinfo=timezone.utc); return s,s+timedelta(days=7)
    if tf=="1M":
        s=datetime(ts.year,ts.month,1,tzinfo=timezone.utc)
        e=datetime(ts.year+1,1,1,tzinfo=timezone.utc) if ts.month==12 else datetime(ts.year,ts.month+1,1,tzinfo=timezone.utc)
        return s,e
    if tf=="1Y":
        s=datetime(ts.year,1,1,tzinfo=timezone.utc); return s,datetime(ts.year+1,1,1,tzinfo=timezone.utc)
    raise ValueError(f"unsupported timeframe {tf}")
