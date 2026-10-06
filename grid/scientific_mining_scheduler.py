"""Schedule scientific mining only for closed walk-forward splits."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from .scientific_pattern_miner import ScientificPatternMiner

def previous_closed_iso_week(now=None):
    now=now or datetime.now(timezone.utc)
    monday=(now-timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    prev_start=monday-timedelta(days=7)
    iso=prev_start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}",monday

class ScientificMiningScheduler:
    def __init__(self,pool,horizons_ms=(1000,2000,5000,10000,30000,60000)):
        self.pool=pool;self.horizons=tuple(int(x) for x in horizons_ms);self.miner=ScientificPatternMiner()
    async def run_closed_split_once(self,now=None):
        split,cutoff=previous_closed_iso_week(now)
        results=[]
        for h in self.horizons:
            family=f"combinatorial-v1|h={h}|fv={self.miner.feature_version}"
            exists=await self.pool.fetchval("""SELECT EXISTS(
              SELECT 1 FROM scientific_mining_runs
              WHERE family_key=$1 AND split_key=$2 AND status='DONE')""",family,split)
            if exists:continue
            results.append(await self.miner.mine_split(self.pool,h,split,cutoff))
        return {"split_key":split,"dataset_cutoff":cutoff,"runs":results}
