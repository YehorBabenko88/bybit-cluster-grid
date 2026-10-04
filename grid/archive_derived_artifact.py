from __future__ import annotations
import gzip,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

FORMAT="archive-derived-v1"


def _row_payload(row):
    levels=[]
    for price,level in sorted((row.get("levels") or {}).items(),key=lambda x:float(x[0])):
        levels.append([float(price),float(level["buy"]),float(level["sell"]),
                       int(level["buy_count"]),int(level["sell_count"])])
    ts=row["ts"]
    if isinstance(ts,datetime):
        ts=ts.astimezone(timezone.utc).isoformat()
    return {"symbol":str(row["symbol"]),"ts":str(ts),
            "open":float(row["open"]),"high":float(row["high"]),
            "low":float(row["low"]),"close":float(row["close"]),
            "buy_volume":float(row["buy_volume"]),"sell_volume":float(row["sell_volume"]),
            "delta":float(row["delta"]),"trade_count":int(row["trade_count"]),
            "poc_price":float(row["poc_price"]),"levels":levels}


def write_derived_artifact(path,rows,metadata):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    count=levels=source_rows=0;min_ts=max_ts=None
    with open(path,"wb") as raw:
        with gzip.GzipFile(filename="",mode="wb",fileobj=raw,mtime=0) as gz:
            header={"format":FORMAT,"metadata":metadata}
            gz.write((json.dumps(header,sort_keys=True,separators=(",",":"))+"\n").encode())
            for row in rows:
                payload=_row_payload(row)
                encoded=(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode()
                gz.write(encoded)
                count+=1;levels+=len(payload["levels"]);source_rows+=payload["trade_count"]
                ts=payload["ts"];min_ts=ts if min_ts is None else min(min_ts,ts);max_ts=ts if max_ts is None else max(max_ts,ts)
    h=hashlib.sha256();size=0
    with open(path,"rb") as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk);size+=len(chunk)
    return {"path":str(path),"sha256":h.hexdigest(),"bytes":size,"derived_candles":count,
            "derived_footprint_rows":levels,"source_rows":source_rows,
            "min_ts":min_ts,"max_ts":max_ts,"format":FORMAT}


def iter_derived_artifact(path,expected_metadata=None):
    with gzip.open(path,"rt",encoding="utf-8") as f:
        first=f.readline()
        if not first:raise ValueError("empty derived archive artifact")
        header=json.loads(first)
        if header.get("format")!=FORMAT:raise ValueError("unsupported derived archive artifact format")
        metadata=dict(header.get("metadata") or {})
        for key,value in (expected_metadata or {}).items():
            if str(metadata.get(key))!=str(value):
                raise ValueError(f"derived archive metadata {key} mismatch")
        for line in f:
            if not line.strip():continue
            p=json.loads(line)
            ts=datetime.fromisoformat(str(p["ts"]).replace("Z","+00:00")).astimezone(timezone.utc)
            levels={float(x[0]):{"buy":float(x[1]),"sell":float(x[2]),
                                 "buy_count":int(x[3]),"sell_count":int(x[4])}
                    for x in p.get("levels") or []}
            yield {"symbol":str(p["symbol"]),"ts":ts,"open":float(p["open"]),
                   "high":float(p["high"]),"low":float(p["low"]),"close":float(p["close"]),
                   "buy_volume":float(p["buy_volume"]),"sell_volume":float(p["sell_volume"]),
                   "delta":float(p["delta"]),"trade_count":int(p["trade_count"]),
                   "poc_price":float(p["poc_price"]),"levels":levels}


def inspect_derived_artifact(path,expected_metadata=None):
    candles=levels=source_rows=0;min_ts=max_ts=None
    for row in iter_derived_artifact(path,expected_metadata):
        candles+=1;levels+=len(row["levels"]);source_rows+=int(row["trade_count"])
        ts=row["ts"];min_ts=ts if min_ts is None else min(min_ts,ts);max_ts=ts if max_ts is None else max(max_ts,ts)
    return {"source_rows":source_rows,"derived_candles":candles,
            "derived_footprint_rows":levels,"min_ts":min_ts,"max_ts":max_ts}
