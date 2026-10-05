import collections,time

class ResourceTrend:
    """Small bounded window for detecting sustained process RSS growth."""
    def __init__(self,max_samples=120):
        self.samples=collections.deque(maxlen=max(10,int(max_samples)))

    def add(self,rss,ts=None):
        self.samples.append((float(ts if ts is not None else time.time()),int(rss)))
        return self.snapshot()

    def snapshot(self):
        if not self.samples:return {"samples":0,"rss_growth_bytes":0,"rss_peak":0,"sustained_growth":False}
        vals=[x[1] for x in self.samples]
        growth=vals[-1]-vals[0]
        # Alert only when a meaningful window is full-ish and most quartile checkpoints rise.
        n=len(vals)
        points=[vals[min(n-1,int((n-1)*q))] for q in (0,.25,.5,.75,1)]
        monotonic=sum(b>=a for a,b in zip(points,points[1:]))>=4
        sustained=n>=20 and monotonic and growth>=256*1024*1024
        return {"samples":n,"rss_growth_bytes":growth,"rss_peak":max(vals),"sustained_growth":sustained}
