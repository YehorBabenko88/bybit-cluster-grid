import asyncio,json,os,time
from pathlib import Path
from .pilot_state import ensure_pilot,update_pilot
from .pilot_readiness import evaluate_pilot

class PilotBootstrap:
    def __init__(self,pool,node_id,source_path,research_path,pause_flag=None):
        self.pool=pool;self.node_id=node_id;self.source_path=source_path;self.research_path=research_path
        self.pause_flag=pause_flag or os.path.join(os.environ.get("ProgramData",r"C:\ProgramData"),"BybitClusterGrid","bootstrap.pause")

    async def wait_if_paused(self):
        while os.path.exists(self.pause_flag):
            await update_pilot(self.pool,self.node_id,paused=True)
            await asyncio.sleep(2)
        await update_pilot(self.pool,self.node_id,paused=False)

    async def report(self,phase,progress,**details):
        await self.wait_if_paused()
        await update_pilot(self.pool,self.node_id,phase=phase,progress=float(progress),details=details)

    async def begin(self):
        if not Path(self.source_path).exists():raise FileNotFoundError(self.source_path)
        await ensure_pilot(self.pool,self.node_id,self.source_path,self.research_path)
        await update_pilot(self.pool,self.node_id,mode="PILOT_BOOTSTRAP",phase="INVENTORY",progress=0,
                           details={"history_repaired":False,"levels_complete":False,"research_complete":False,
                                    "import_verified":False,"live_canary_healthy":False})

    async def complete_history(self,coverage):
        await self.report("LEVEL_RESEARCH",40,history_repaired=True,coverage=coverage)

    async def complete_research(self,summary):
        await self.report("IMPORT",70,levels_complete=True,research_complete=True,research_summary=summary)

    async def complete_import(self,manifest):
        await self.report("LIVE_CANARY",90,import_verified=True,import_manifest=manifest)
        await update_pilot(self.pool,self.node_id,mode="PILOT_VALIDATING")

    async def complete_live_canary(self,health):
        state=await self.pool.fetchrow("SELECT details FROM pilot_bootstrap_state WHERE node_id=$1",self.node_id)
        raw_details = state["details"] if state else None
        if isinstance(raw_details, str):
            details = json.loads(raw_details)
        elif isinstance(raw_details, dict):
            details = dict(raw_details)
        elif raw_details is None:
            details = {}
        else:
            raise TypeError("Unexpected pilot details type")
        if not isinstance(details, dict):
            raise TypeError("Pilot details must be a JSON object")
        details["live_canary_healthy"] = True
        details["live_canary"] = health
        return await evaluate_pilot(self.pool,self.node_id,details)
