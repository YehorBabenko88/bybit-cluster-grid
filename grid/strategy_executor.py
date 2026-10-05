import hashlib, logging, os, pathlib, sys
from .config import settings
from .strategy_plugins import get_plugin
from .ml_process_supervisor import run_supervised_process

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
    ram_limit_mb=max(256,int(float(getattr(settings,"strategy_ram_limit_mb",4096))))
    stdout=await run_supervised_process(
        [sys.executable,"-m","grid.strategy_runtime"],
        timeout_seconds=getattr(settings,"strategy_job_timeout_seconds",21600),
        ram_limit_mb=ram_limit_mb,
        poll_seconds=.5,
        grace_seconds=5,
        env=env,
    )
    return (stdout or b"").decode("utf-8","replace")
