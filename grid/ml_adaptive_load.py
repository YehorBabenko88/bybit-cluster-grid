class AdaptiveConcurrency:
    """Hysteretic concurrency controller: protects collection/database before ML throughput."""
    def __init__(self,min_workers=0,max_workers=4):
        self.min=int(min_workers); self.max=int(max_workers); self.current=min(1,self.max); self.good=0
    def update(self,cpu_pct,ram_pct,db_latency_ms,db_queue_ratio,disk_free_gb):
        danger=cpu_pct>=85 or ram_pct>=88 or db_latency_ms>=250 or db_queue_ratio>=.80 or disk_free_gb<20
        healthy=cpu_pct<60 and ram_pct<70 and db_latency_ms<80 and db_queue_ratio<.35 and disk_free_gb>=40
        if danger:
            self.good=0; self.current=max(self.min,self.current-1)
        elif healthy:
            self.good+=1
            if self.good>=6:
                self.current=min(self.max,self.current+1); self.good=0
        else:self.good=0
        return self.current
