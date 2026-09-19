from __future__ import annotations
import argparse,asyncio,json,os,sqlite3
from pathlib import Path
from .service import prepare_database,bootstrap_logging
from .config import settings
from .bybit import linear_symbols
from .pilot_checkpoint import PilotCheckpoint
from .pilot_inventory import inventory,verified_inventory
from .legacy_gap_repair import repair_gaps
from .legacy_research_adapter import run_research_command
from .legacy_bootstrap_import import import_handoff
from .pilot_bootstrap import PilotBootstrap

def lifecycle_map(items):
    out={}
    for x in items:
        meta=x.get("metadata") or x
        out[x["symbol"]]={"status":meta.get("status","TRADING"),
                          "delivery_time_ms":meta.get("deliveryTime") or meta.get("delivery_time")}
    return out

async def run(args):
    db=await prepare_database()
    cp=PilotCheckpoint(args.checkpoint);state=cp.initialize(args.sqlite)
    pilot=PilotBootstrap(db.pool,args.node_id,args.sqlite,args.output)
    await pilot.begin()
    try:
        cutoff=int(state["research_cutoff_ms"])
        current=await linear_symbols(settings.bybit_rest_url);life=lifecycle_map(current)
        if state["stage"] in ("INVENTORY","REPAIR"):
            inv=inventory(args.sqlite,cutoff,life)
            await pilot.report("REPAIR_HISTORY",10,gap_minutes=inv["gap_minutes"],symbols=inv["symbols"])
            cp.advance("REPAIR",gap_minutes=inv["gap_minutes"])
            if inv["gaps"]:
                conn=sqlite3.connect(args.sqlite,timeout=60)
                try:
                    await repair_gaps(conn,settings.bybit_rest_url,inv["gaps"],pilot.pause_flag)
                finally:conn.close()
            cp.advance("VERIFY_REPAIR")
        state=cp.load()
        inv=verified_inventory(args.sqlite,cutoff,life)
        await pilot.complete_history({"symbols":inv["symbols"],"gap_minutes":0,"cutoff_ms":cutoff})
        if state["stage"] in ("VERIFY_REPAIR","RESEARCH"):
            cp.advance("RESEARCH",coverage_symbols=inv["symbols"])
            handoff,data=await run_research_command(args.research_command,args.sqlite,cutoff,args.output,pilot.pause_flag)
            cp.advance("IMPORT",handoff=handoff)
            await pilot.complete_research({"handoff":handoff})
        else:
            handoff=state.get("handoff")
        state=cp.load()
        if state["stage"]=="IMPORT":
            if not handoff:raise RuntimeError("IMPORT checkpoint has no handoff")
            result=await import_handoff(db.pool,handoff)
            cp.advance("LIVE_CANARY",import_result=result)
            await pilot.complete_import(result)
        else:
            result=state.get("import_result")
        return {"stage":"LIVE_CANARY","cutoff_ms":cutoff,"import":result}
    finally:
        if db.pool:await db.pool.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--node-id",required=True);p.add_argument("--sqlite",required=True)
    p.add_argument("--research-command",required=True);p.add_argument("--output",required=True)
    p.add_argument("--checkpoint",required=True)
    a=p.parse_args();bootstrap_logging();print(json.dumps(asyncio.run(run(a)),indent=2,default=str))
if __name__=="__main__":main()
