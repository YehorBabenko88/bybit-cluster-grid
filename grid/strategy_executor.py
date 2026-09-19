import asyncio, hashlib, logging, os, pathlib, sys
from .config import settings
from .strategy_plugins import get_plugin

log=logging.getLogger("strategy_executor")

def _safe_piece(s):
    return "".join(ch for ch in str(s) if ch.isalnum() or ch in "._-")

async def materialize_plugin(pool,name,version):
    plugin=await get_plugin(pool,name,version)
    if not plugin:
        raise RuntimeError(f"strategy plugin unavailable: {name} v{version}")
    source=plugin["source_code"]
    sha=hashlib.sha256(source.encode("utf-8")).hexdigest()
    if sha != plugin["sha256"]:
        raise RuntimeError("strategy plugin SHA256 mismatch")

    root=pathlib.Path(getattr(settings,"strategy_cache_dir","runtime_strategies"))
    path=root/_safe_piece(name)/_safe_piece(version)/sha
    path.mkdir(parents=True,exist_ok=True)
    target=path/"strategy.py"
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
        tmp=target.with_suffix(".tmp")
        tmp.write_text(source,encoding="utf-8")
        os.replace(tmp,target)
    return target

async def execute_job_subprocess(db,job):
    plugin_path=await materialize_plugin(db.pool,job["strategy_name"],job["strategy_version"])
    env=os.environ.copy()
    env["GRID_STRATEGY_PLUGIN"]=str(plugin_path.resolve())
    env["GRID_STRATEGY_JOB_ID"]=str(job["id"])
    env["POSTGRES_DSN"]=settings.postgres_dsn

    proc=await asyncio.create_subprocess_exec(
        sys.executable,"-m","grid.strategy_runtime",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout,stderr=await asyncio.wait_for(
            proc.communicate(),
            timeout=getattr(settings,"strategy_job_timeout_seconds",21600)
        )
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        raise RuntimeError("strategy job timeout")
    if proc.returncode!=0:
        msg=(stderr or stdout or b"strategy subprocess failed").decode("utf-8","replace")[-6000:]
        raise RuntimeError(msg)
    return (stdout or b"").decode("utf-8","replace")
