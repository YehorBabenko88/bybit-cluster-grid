import csv,gzip,io,zipfile
from .trade_archive_transform import normalize_archive_trade,aggregate_minute

def _iter_csv_text(stream):
    wrapper=io.TextIOWrapper(stream,encoding="utf-8-sig",errors="replace",newline="")
    yield from csv.DictReader(wrapper)

def iter_archive_rows(path):
    lower=path.lower()
    if lower.endswith(".gz"):
        with gzip.open(path,"rb") as f:yield from _iter_csv_text(f)
    elif lower.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(names)!=1:raise ValueError("archive must contain exactly one CSV")
            with z.open(names[0],"r") as f:yield from _iter_csv_text(f)
    else:
        with open(path,"rb") as f:yield from _iter_csv_text(f)

def iter_minute_aggregates(path,symbol,tick_size):
    minute=[];current=None;seen_ids=set();last_ts=None
    for raw in iter_archive_rows(path):
        t=normalize_archive_trade(raw)
        if last_ts is not None and t["ts"] < last_ts:
            raise ValueError("archive trades are not monotonically ordered")
        last_ts=t["ts"]
        key=t["ts"].replace(second=0,microsecond=0)
        if current is not None and key!=current:
            for x in aggregate_minute(symbol,minute,tick_size):yield x
            minute=[];seen_ids=set()
        current=key
        trade_id=t["trade_id"]
        if trade_id in seen_ids:
            continue
        seen_ids.add(trade_id);minute.append(t)
    if minute:
        for x in aggregate_minute(symbol,minute,tick_size):yield x
