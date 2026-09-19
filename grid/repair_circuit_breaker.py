import time

class RepairCircuitBreaker:
    def __init__(self,max_attempts=3,window_seconds=3600,cooldown_seconds=1800):
        self.max_attempts=int(max_attempts);self.window=float(window_seconds);self.cooldown=float(cooldown_seconds)
        self.history={};self.blocked_until={}
    def allow(self,node_id,now=None):
        now=time.time() if now is None else float(now)
        if now<self.blocked_until.get(node_id,0):return False
        xs=[x for x in self.history.get(node_id,[]) if now-x<=self.window]
        self.history[node_id]=xs
        if len(xs)>=self.max_attempts:
            self.blocked_until[node_id]=now+self.cooldown
            return False
        return True
    def record(self,node_id,now=None):
        now=time.time() if now is None else float(now)
        self.history.setdefault(node_id,[]).append(now)
