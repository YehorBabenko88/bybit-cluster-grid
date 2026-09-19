from __future__ import annotations
import asyncio,json,os,shlex
from pathlib import Path
from .pilot_inventory import verified_inventory

async def run_research_command(command,source_db,cutoff_ms,output_dir,pause_flag=None):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    env.update({"GRID_LEGACY_DB":str(Path(source_db).resolve()),
                "GRID_RESEARCH_CUTOFF_MS":str(int(cutoff_ms)),
                "GRID_RESEARCH_OUTPUT":str(out.resolve())})
    while pause_flag and os.path.exists(pause_flag):await asyncio.sleep(2)
    proc=await asyncio.create_subprocess_exec(*shlex.split(command,posix=os.name!="nt"),
      env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
    log=out/"research.log"
    with log.open("ab") as f:
        while True:
            line=await proc.stdout.readline()
            if not line:break
            f.write(line);f.flush()
    rc=await proc.wait()
    if rc:raise RuntimeError(f"research process failed rc={rc}; see {log}")
    handoff=out/"grid_handoff.json"
    if not handoff.exists():raise RuntimeError("research completed without grid_handoff.json")
    data=json.loads(handoff.read_text(encoding="utf-8"))
    if data.get("phase")!="GRID_IMPORT_PENDING" or not data.get("cache_repair_complete"):
        raise RuntimeError("research handoff is not import-ready")
    if int(data.get("research_cutoff_ms",-1))!=int(cutoff_ms):
        raise RuntimeError("research cutoff differs from frozen pilot cutoff")
    inv=verified_inventory(source_db,cutoff_ms)
    data["source_candle_db"]=str(Path(source_db).resolve())
    data["coverage"]=[{k:v for k,v in row.items() if k!="coverage_fingerprint"} for row in inv["coverage"]]
    data["coverage_fingerprints"]={row["symbol"]:row["coverage_fingerprint"] for row in inv["coverage"]}
    tmp=handoff.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
    os.replace(tmp,handoff)
    return str(handoff),data
