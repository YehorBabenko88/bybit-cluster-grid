from __future__ import annotations
import json
from datetime import timedelta


class ContinuousMicrostructureSamples:
    """Turn live microstructure snapshots into causally labelled training rows.

    Features are frozen at known_at. Targets are written only after the full
    future candle horizon exists, so training never observes partial futures.
    """
    def __init__(self,pool,horizons_seconds=(60,300,900),max_snapshot_age_seconds=2):
        self.pool=pool
        self.horizons=tuple(sorted({int(x) for x in horizons_seconds if int(x)>0}))
        self.max_snapshot_age_seconds=int(max_snapshot_age_seconds)

    async def materialize(self,symbol,through_ts):
        snapshots=await self.pool.fetch("""SELECT symbol,ts,known_at,payload
          FROM microstructure_samples
          WHERE symbol=$1 AND known_at<=$2 ORDER BY known_at""",symbol,through_ts)
        rows=[]
        for s in snapshots:
            payload=_obj(s["payload"])
            quality=_quality(payload)
            for horizon in self.horizons:
                label_end=s["ts"]+timedelta(seconds=horizon)
                rows.append((symbol,s["ts"],s["known_at"],horizon,json.dumps(payload),
                             label_end,quality))
        if rows:
            await self.pool.executemany("""INSERT INTO microstructure_ml_samples
              (symbol,feature_ts,known_at,horizon_seconds,features,label_end_ts,quality_status)
              VALUES($1,$2,$3,$4,$5::jsonb,$6,$7)
              ON CONFLICT(symbol,feature_ts,horizon_seconds) DO NOTHING""",rows)
        return len(rows)

    async def label_ready(self,symbol,through_ts):
        pending=await self.pool.fetch("""SELECT id,feature_ts,known_at,horizon_seconds,features,label_end_ts
          FROM microstructure_ml_samples
          WHERE symbol=$1 AND target_ready=false AND label_end_ts<=$2
          ORDER BY feature_ts,id""",symbol,through_ts)
        labelled=0
        for sample in pending:
            # Use only completed one-minute candles strictly after feature time.
            bars=await self.pool.fetch("""SELECT ts,open,high,low,close FROM candles_1m
              WHERE symbol=$1 AND ts>$2 AND ts<=$3 ORDER BY ts""",
              symbol,sample["feature_ts"],sample["label_end_ts"])
            target=_target(sample,bars)
            if target is None:
                continue
            await self.pool.execute("""UPDATE microstructure_ml_samples
              SET target=$2::jsonb,target_ready=true
              WHERE id=$1 AND target_ready=false""",sample["id"],json.dumps(target))
            labelled+=1
        return labelled


def _target(sample,bars):
    horizon=int(sample["horizon_seconds"])
    expected=max(1,horizon//60)
    if len(bars)<expected:
        return None
    features=_obj(sample["features"])
    bid=_float(features.get("bid")); ask=_float(features.get("ask"))
    reference=(bid+ask)/2.0 if bid and ask else _float(bars[0].get("open") if hasattr(bars[0],"get") else bars[0]["open"])
    if not reference:
        return None
    highs=[float(x["high"]) for x in bars[:expected]]
    lows=[float(x["low"]) for x in bars[:expected]]
    close=float(bars[expected-1]["close"])
    future_return=close/reference-1.0
    return {
        "horizon_seconds":horizon,
        "reference_price":reference,
        "future_return":future_return,
        "mfe":max(highs)/reference-1.0,
        "mae":min(lows)/reference-1.0,
        "up":future_return>0.0,
        "bars":expected,
    }


def _obj(value):
    if isinstance(value,dict): return dict(value)
    if isinstance(value,str):
        try:
            x=json.loads(value)
            return x if isinstance(x,dict) else {}
        except Exception: return {}
    try: return dict(value)
    except Exception: return {}


def _float(value):
    try: return float(value)
    except (TypeError,ValueError): return 0.0


def _quality(payload):
    q=payload.get("_quality") or {}
    book=q.get("orderbook") if isinstance(q,dict) else None
    if payload.get("book_gap") or payload.get("trade_gap"):
        return "DEGRADED"
    if isinstance(book,dict) and book.get("status") not in (None,"AVAILABLE"):
        return "DEGRADED"
    return "GOOD"
