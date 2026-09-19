import asyncio, logging, os, subprocess, sys
from .update_manager import rollback
log=logging.getLogger("agent_commands")

async def execute_command(worker,cmd):
    action=cmd["action"]; payload=cmd.get("payload") or {}
    if action=="pause":
        worker.enabled=False
        await worker.reconcile()
        return {"state":"paused"}
    if action=="resume":
        worker.enabled=True
        await worker.reconcile()
        return {"state":"running"}
    if action=="restart":
        # Supervisor/Task Scheduler restarts the process after this clean exit.
        asyncio.get_running_loop().call_later(1.0,lambda:os._exit(75))
        return {"state":"restarting"}
    if action=="rollback":
        version=rollback(payload["install_root"])
        if not version: raise RuntimeError("no previous release")
        asyncio.get_running_loop().call_later(1.0,lambda:os._exit(75))
        return {"state":"rollback","version":version}
    if action=="uninstall":
        # Never delete data unless purge_data=true was explicitly included.
        script=payload.get("script")
        if not script: raise RuntimeError("uninstall script path missing")
        args=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",script]
        if payload.get("purge_data"): args.append("--purge-data")
        subprocess.Popen(args,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        return {"state":"uninstall_started"}
    raise ValueError(f"unsupported command: {action}")
