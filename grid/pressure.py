import time
from dataclasses import dataclass, field

NORMAL="NORMAL"
SOFT_PRESSURE="SOFT_PRESSURE"
REDUCE_LOAD="REDUCE_LOAD"
CRITICAL="CRITICAL"

@dataclass
class PressureController:
    cpu_limit: float=75
    ram_limit: float=78
    min_disk_gb: float=25
    state: str=NORMAL
    bad_ticks: int=0
    good_ticks: int=0
    symbol_cost: dict=field(default_factory=dict)

    def observe_symbol(self,symbol,events=0,db_writes=0,alpha=.2):
        score=max(0.0,float(events))+2.0*max(0.0,float(db_writes))
        old=self.symbol_cost.get(symbol,score)
        self.symbol_cost[symbol]=(1-alpha)*old+alpha*score

    def update(self,snap,queue_ratio=0.0):
        cpu=float(snap.get("cpu_pct",0))
        ram=float(snap.get("ram_pct",0))
        disk=float(snap.get("disk_free",0))/(1024**3)
        disk_state=str(snap.get("disk_pressure_state","NORMAL"))
        severe=(cpu>=min(95,self.cpu_limit+15) or ram>=min(95,self.ram_limit+12)
                or disk_state in ("HARD","EMERGENCY")
                or disk<max(2,self.min_disk_gb*.4) or queue_ratio>=.95)
        pressured=(cpu>=self.cpu_limit or ram>=self.ram_limit
                   or disk_state!="NORMAL"
                   or disk<self.min_disk_gb or queue_ratio>=.75)
        if severe:
            self.bad_ticks+=2; self.good_ticks=0
        elif pressured:
            self.bad_ticks+=1; self.good_ticks=0
        else:
            self.good_ticks+=1; self.bad_ticks=max(0,self.bad_ticks-1)

        if severe and self.bad_ticks>=4: self.state=CRITICAL
        elif self.bad_ticks>=6: self.state=REDUCE_LOAD
        elif self.bad_ticks>=2: self.state=SOFT_PRESSURE
        elif self.good_ticks>=6: self.state=NORMAL
        return self.state

    def symbols_to_drain(self,assigned):
        assigned=list(assigned)
        if self.state in (NORMAL,SOFT_PRESSURE) or not assigned: return []
        fraction=.5 if self.state==CRITICAL else .25
        count=max(1,int(len(assigned)*fraction))
        return sorted(assigned,key=lambda s:(self.symbol_cost.get(s,0),s),reverse=True)[:count]


def desired_drained_symbols(controller, assigned):
    """Compute a fresh bounded drain set from the complete assignment."""
    return set(controller.symbols_to_drain(assigned))
