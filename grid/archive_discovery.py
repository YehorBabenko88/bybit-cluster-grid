import re
from datetime import date,datetime,timedelta,timezone
from html.parser import HTMLParser
import aiohttp

class _HrefParser(HTMLParser):
    def __init__(self):
        super().__init__();self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="a":return
        for k,v in attrs:
            if k.lower()=="href" and v:self.hrefs.append(v)

def parse_archive_dates(symbol,html):
    p=_HrefParser();p.feed(html)
    rx=re.compile(re.escape(symbol)+r"(\d{4}-\d{2}-\d{2})\.csv\.gz$",re.I)
    out=[]
    for href in p.hrefs:
        name=href.rsplit("/",1)[-1]
        m=rx.search(name)
        if m:
            try:out.append(date.fromisoformat(m.group(1)))
            except ValueError:pass
    return sorted(set(out))

def archive_url(base_url,symbol,day):
    return f"{base_url.rstrip('/')}/{symbol}/{symbol}{day.isoformat()}.csv.gz"

async def list_symbol_archives(base_url,symbol,timeout=30):
    url=f"{base_url.rstrip('/')}/{symbol}/"
    async with aiohttp.ClientSession() as s:
        async with s.get(url,timeout=timeout) as r:
            if r.status==404:return {"mode":"LISTING","dates":[],"status":"UNAVAILABLE","url":url}
            r.raise_for_status()
            text=await r.text(errors="replace")
    dates=parse_archive_dates(symbol,text)
    return {"mode":"LISTING","dates":dates,
            "status":"READY" if dates else "EMPTY","url":url}

async def probe_day(base_url,symbol,day,timeout=20):
    url=archive_url(base_url,symbol,day)
    headers={"Range":"bytes=0-0"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url,headers=headers,timeout=timeout) as r:
            if r.status in (200,206):
                size=r.headers.get("Content-Range") or r.headers.get("Content-Length")
                return {"available":True,"url":url,"size_hint":size,"status":r.status}
            if r.status==404:return {"available":False,"url":url,"status":404}
            if 500<=r.status<600:raise RuntimeError(f"archive probe temporary HTTP {r.status}")
            return {"available":False,"url":url,"status":r.status}

async def fallback_probe(base_url,symbol,days=30,end_day=None):
    end_day=end_day or (datetime.now(timezone.utc).date()-timedelta(days=1))
    found=[]
    for i in range(max(1,int(days))):
        d=end_day-timedelta(days=i)
        r=await probe_day(base_url,symbol,d)
        if r["available"]:found.append((d,r["url"]))
    return {"mode":"PROBE","status":"PARTIAL" if found else "UNAVAILABLE",
            "dates":[d for d,_ in found],"urls":{d:u for d,u in found}}
