import asyncio
import json, logging, secrets, time, os, pathlib, subprocess
from datetime import datetime, timedelta, timezone
import aiohttp
from .config import settings
from .control_plane import enqueue_command
from .db_stats import database_stats
from .retention import cleanup_all
from .update_protocol import start_canary
from .control_replication import telegram_cursor,commit_telegram_cursor
from .fleet_health import fleet_health
from .pilot_state import pilot_state,expansion_ready,mark_expansion_notified
from .retention_plan import cleanup_plan
from .retention import RETENTION_DEFAULTS
from .telegram_idempotency import claim_update,complete_update
from .ha_status import ha_status
from .runtime_gate import runtime_state,set_runtime_state
from .fleet_control import fleet_stop,fleet_resume,begin_fleet_delete,fleet_delete_status,latest_operation,reconcile_fleet_operation
from .start_readiness import start_readiness
from .enrollment import create_enrollment_token
from .server_pilot import begin_server_pilot_validation

log=logging.getLogger("telegram")
_pending_confirms={}

def _decode_command_result(value):
    if not value:
        return {}
    if isinstance(value,dict):
        return value
    if isinstance(value,str):
        try:
            decoded=json.loads(value)
        except (TypeError,ValueError):
            return {"message":value}
        return decoded if isinstance(decoded,dict) else {"message":value}
    return {"message":str(value)}

def allowed(chat_id):
    raw={x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()}
    return bool(raw) and str(chat_id) in raw

def _node_keyboard(nid):
    return {"inline_keyboard":[
      [{"text":"⏸ PAUSE","callback_data":f"node:pause:{nid}"},{"text":"▶ START","callback_data":f"node:start:{nid}"}],
      [{"text":"⏹ STOP","callback_data":f"node:stop:{nid}"},{"text":"⏯ RESUME","callback_data":f"node:resume:{nid}"}],
      [{"text":"🔄 RESTART","callback_data":f"node:restart:{nid}"},{"text":"📄 LOGS","callback_data":f"node:logs:{nid}"}],
      [{"text":"🗑 УДАЛИТЬ АГЕНТ","callback_data":f"node:uninstall:{nid}"},{"text":"⬅ ВСЕ АГЕНТЫ","callback_data":"fleet:nodes"}]
    ]}

def _nodes_keyboard(nodes):
    rows=[[{"text":f"🖥 {nid}","callback_data":f"node:show:{nid}"}] for nid in sorted(nodes)]
    rows.append([{"text":"⬅ ГЛАВНОЕ МЕНЮ","callback_data":"fleet:menu"}])
    return {"inline_keyboard":rows}

def _main_keyboard():
    return {"inline_keyboard":[
      [{"text":"▶ НАЧАТЬ","callback_data":"fleet:begin"},{"text":"⏹ СТОП","callback_data":"fleet:stop"}],
      [{"text":"⏯ ПРОДОЛЖИТЬ","callback_data":"fleet:resume"},{"text":"🗑 УДАЛИТЬ","callback_data":"fleet:delete"}],
      [{"text":"🖥 АГЕНТЫ","callback_data":"fleet:nodes"},{"text":"ℹ СОСТОЯНИЕ","callback_data":"fleet:system"}],
      [{"text":"🧠 RESEARCH","callback_data":"fleet:research"},{"text":"📦 ARCHIVE","callback_data":"fleet:archive"}],
      [{"text":"🗄 STORAGE","callback_data":"fleet:storage"},{"text":"⚠ ERRORS","callback_data":"fleet:errors"}]
    ]}

async def tg_send(session,chat_id,text,reply_markup=None):
    url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    body={"chat_id":chat_id,"text":text[:4000]}
    if reply_markup: body["reply_markup"]=reply_markup
    async with session.post(url,json=body,timeout=15) as r:
        payload=await r.json(content_type=None)
        if r.status!=200 or not bool(payload.get("ok")):
            raise RuntimeError(f"Telegram send failed status={r.status}: {str(payload)[:500]}")

def _node_line(nid,n,now):
    age=max(0,int(now-float(n.get("last_seen",0))))
    state="ONLINE" if age < settings.heartbeat_seconds*3 else "OFFLINE"
    return f"{nid}: {state}, v={n.get('agent_version','?')}, cpu={n.get('cpu_pct','?')}%, ram={n.get('ram_pct','?')}%, seen={age}s"

def _healthy_canary(nodes):
    now=time.time()
    candidates=[]
    for nid,n in nodes.items():
        if now-float(n.get("last_seen",0)) >= settings.heartbeat_seconds*3: continue
        cpu=float(n.get("cpu_pct",100) or 100)
        ram=float(n.get("ram_pct",100) or 100)
        disk=float(n.get("disk_free",0) or 0)/(1024**3)
        if cpu>=settings.resource_cpu_limit or ram>=settings.resource_ram_limit or disk<settings.resource_disk_free_gb:
            continue
        candidates.append((cpu+ram,nid))
    return min(candidates)[1] if candidates else None

async def system_overview(db,nodes):
    now=time.time()
    runtime=await runtime_state(db.pool)
    online=sum(1 for n in nodes.values() if now-float(n.get("last_seen",0))<settings.heartbeat_seconds*3)
    research=await db.pool.fetchrow("""SELECT
      count(*) FILTER (WHERE status IN ('BUILDING','QUEUED','RUNNING')) active,
      count(*) FILTER (WHERE status='FAILED') failed FROM research_runs""")
    archive=await db.pool.fetchrow("""SELECT
      count(*) FILTER (WHERE status IN ('queued','running')) active,
      count(*) FILTER (WHERE status='failed') failed,
      count(*) FILTER (WHERE status='done' AND materialized_at IS NULL) pending_materialize
      FROM archive_compute_jobs""")
    compute=await db.pool.fetchrow("""SELECT
      count(*) FILTER (WHERE status IN ('queued','assigned','running')) active,
      count(*) FILTER (WHERE status='failed') failed FROM ml_jobs""")
    return {
      "runtime":runtime,"nodes":len(nodes),"online":online,
      "research_active":int(research["active"] or 0),"research_failed":int(research["failed"] or 0),
      "archive_active":int(archive["active"] or 0),"archive_failed":int(archive["failed"] or 0),
      "archive_pending_materialize":int(archive["pending_materialize"] or 0),
      "compute_active":int(compute["active"] or 0),"compute_failed":int(compute["failed"] or 0),
    }


async def handle_command(db,session,chat_id,text,nodes):
    parts=text.strip().split()
    cmd=parts[0].lower()
    now=time.time()
    if cmd=="/menu" or (cmd=="/start" and len(parts)==1):
        await tg_send(session,chat_id,"Управление Bybit Cluster Grid",_main_keyboard())
    elif cmd=="/system":
        o=await system_overview(db,nodes);s=o["runtime"]
        await tg_send(session,chat_id,
          f"SYSTEM: {s['state']}\nNodes: {o['nodes']}, online: {o['online']}\n"
          f"Market data: {'ENABLED' if s['state']=='ACTIVE' else 'LOCKED'}\n"
          f"Compute: active={o['compute_active']} failed={o['compute_failed']}\n"
          f"Research: active={o['research_active']} failed={o['research_failed']}\n"
          f"Archive: active={o['archive_active']} pending-materialize={o['archive_pending_materialize']} failed={o['archive_failed']}\n"
          f"Reason: {s.get('reason') or '-'}",_main_keyboard())
    elif cmd in ("/joinpilot","/joinagent"):
        mode="PILOT" if cmd=="/joinpilot" else "NORMAL"
        label=parts[1] if len(parts)>1 else f"telegram:{chat_id}"
        expires=datetime.now(timezone.utc)+timedelta(minutes=15)
        try:
            token=await create_enrollment_token(db.pool,label,expires,mode)
        except ValueError as e:
            await tg_send(session,chat_id,f"Enrollment rejected: {e}")
            return
        await tg_send(
            session,chat_id,
            f"{mode} enrollment token (one use, expires in 15 minutes):\n{token}\n"
            "Run the signed/hash-verified onboarding bundle as Administrator on the new Windows PC. "
            "The client does not choose its server-authorized role."
        )
    elif cmd=="/begin":
        s=await runtime_state(db.pool)
        if s["state"]=="ACTIVE":
            await tg_send(session,chat_id,"System is already ACTIVE.")
            return
        if s["state"]!="INFRA_ONLY":
            await tg_send(session,chat_id,f"START blocked: SYSTEM state is {s['state']}.")
            return
        readiness=await start_readiness(db.pool,nodes,settings.heartbeat_seconds)
        if not readiness["ready"]:
            await tg_send(session,chat_id,"START blocked by readiness gate: "+", ".join(readiness["missing"]))
            return
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("fleet_begin",None,time.time()+120)
        await tg_send(session,chat_id,"START readiness OK. This will enable Bybit discovery, market collection, archive/backfill, feature generation, simulations and learning for the whole Grid.\nConfirm within 120s: /confirm "+code)
    elif cmd in ("/fleetpause","/fleetstop"):
        r=await fleet_stop(db.pool,nodes,f"telegram:{chat_id}")
        await tg_send(session,chat_id,f"SYSTEM: STOPPING. Stop queued for {len(r.get('commands',[]))} agents; STOPPED will be reported only after all required ACKs. Control heartbeat remains online.",_main_keyboard())
    elif cmd=="/fleetresume":
        r=await fleet_resume(db.pool,nodes,f"telegram:{chat_id}")
        kept=r.get("preserved_stopped") or []
        msg=f"SYSTEM: RESUMING. Resume queued for {len(r.get('commands',[]))} agents; ACTIVE will open only after all required ACKs."
        if kept: msg+=" Previously stopped nodes preserved: "+", ".join(kept)
        await tg_send(session,chat_id,msg,_main_keyboard())
    elif cmd=="/fleetdelete":
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("fleet_delete",None,time.time()+120)
        await tg_send(session,chat_id,"DANGER: this will purge Grid software and Grid-owned data from ALL registered computers. CONTROL is deleted LAST, only after every agent acknowledges purge.\nConfirm within 120s: /confirm "+code)
    elif cmd=="/pilot":
        rows=await pilot_state(db.pool,parts[1] if len(parts)>1 else None)
        rows=[rows] if isinstance(rows,dict) else rows
        if not rows:
            await tg_send(session,chat_id,"No pilot bootstrap state.")
        else:
            lines=["Pilot bootstrap:"]
            for r in rows:
                lines.append(f"{r['node_id']}: {r['mode']} / {r['phase']}, progress={float(r['progress']):.1f}%, paused={r['paused']}")
                missing=(r.get("details") or {}).get("missing_readiness")
                if missing: lines.append("  waiting: "+", ".join(missing))
            await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/pilotvalidate":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /pilotvalidate NODE"); return
        nid=parts[1]
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("pilot_validate",nid,time.time()+120)
        await tg_send(
            session,chat_id,
            f"Pilot validation requested for {nid}. This only changes the durable pilot lifecycle; "
            "the global runtime must remain STOPPED and no market workload is opened by this step.\n"
            f"Confirm within 120s: /confirm {code}"
        )
    elif cmd=="/health":
        h=await fleet_health(db.pool,nodes,settings.heartbeat_seconds)
        leader=h["leader"]["owner"] if h["leader"] else "none"
        lines=[f"Grid health: leader={leader}",f"online={len(h['online'])} offline={len(h['offline'])}"]
        lines.append("integrity: "+(", ".join(h["integrity"]) if h["integrity"] else "OK"))
        lines.append("pressure: "+(", ".join(h["pressure"]) if h["pressure"] else "OK"))
        lines.append("DB queue/spool: "+(", ".join(h["queues"]) if h["queues"] else "OK"))
        if h["repairs"]:
            lines.append("repairs: "+", ".join(f"{x['node_id']}={x['status']}" for x in h["repairs"][:5]))
        ha=await ha_status(db.pool,nodes,settings.heartbeat_seconds)
        lines.append(f"HA: {ha['ha_level']}, candidates={ha['control_candidates']}, DB failover={'ON' if ha['automatic_db_failover'] else 'OFF'}")
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/nodes":
        lines=["Grid nodes:"]+[_node_line(nid,n,now) for nid,n in sorted(nodes.items())]
        await tg_send(session,chat_id,"\n".join(lines) if len(lines)>1 else "No nodes registered.")
    elif cmd=="/node":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /node NODE"); return
        nid=parts[1]; n=nodes.get(nid)
        if not n:
            await tg_send(session,chat_id,f"Unknown node: {nid}"); return
        age=max(0,int(now-float(n.get("last_seen",0))))
        p=await pilot_state(db.pool,nid)
        mode=(p or {}).get("mode",n.get("live_mode","NORMAL"))
        syms=n.get("wanted_symbols",0); streams=n.get("active_trade_streams",0)
        assigned=n.get("assigned_symbols") or []
        lines=[f"Node {nid}",f"mode={mode} online={age<settings.heartbeat_seconds*3} seen={age}s",
               f"workload: wanted={syms} streams={streams} stopped={n.get('operator_stopped',False)}",
               f"resources: cpu={n.get('cpu_pct','?')}% ram={n.get('ram_pct','?')}% pressure={n.get('pressure_state','?')}",
               f"storage: queue={n.get('db_queue_ratio','?')} spool={n.get('db_spool_ratio','?')}",
               f"integrity={n.get('integrity_ok','?')} assignments={len(assigned) if isinstance(assigned,list) else syms}"]
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/research":
        if len(parts)>1:
            try: run_id=parts[1]
            except Exception: run_id=parts[1]
            r=await db.pool.fetchrow("""SELECT id,kind,status,dataset_hash,created_at,finished_at,
              aggregate_fingerprint,result_artifact_id,last_error FROM research_runs
              WHERE id::text LIKE $1 ORDER BY created_at DESC LIMIT 1""",str(run_id)+"%")
            if not r:
                await tg_send(session,chat_id,"Unknown research run."); return
            shards=await db.pool.fetch("""SELECT status,count(*) n FROM research_shards
              WHERE run_id=$1 GROUP BY status ORDER BY status""",r["id"])
            await tg_send(session,chat_id,
              f"Research {str(r['id'])}\n{r['kind']}: {r['status']}\n"
              f"dataset={str(r['dataset_hash'])[:16]} fp={(r['aggregate_fingerprint'] or '-')[:16]}\n"
              f"artifact={r['result_artifact_id'] or '-'}\n"
              +"shards: "+", ".join(f"{x['status']}={x['n']}" for x in shards)
              +(f"\nerror={r['last_error']}" if r['last_error'] else ""))
            return
        runs=await db.pool.fetch("""SELECT id,kind,status,created_at,finished_at,aggregate_fingerprint
          FROM research_runs ORDER BY created_at DESC LIMIT 5""")
        jobs=await db.pool.fetchrow("""SELECT count(*) FILTER (WHERE status IN ('queued','assigned','running')) active,
          count(*) FILTER (WHERE status='failed') failed FROM research_shards""")
        lines=[f"Research: active={int(jobs['active'] or 0)} failed={int(jobs['failed'] or 0)}"]
        lines += [f"{str(r['id'])[:8]} {r['kind']}: {r['status']} fp={(r['aggregate_fingerprint'] or '-')[:12]}" for r in runs]
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/archive":
        s=await db.pool.fetchrow("""SELECT
          count(*) FILTER (WHERE status='queued') queued,
          count(*) FILTER (WHERE status='running') running,
          count(*) FILTER (WHERE status='done' AND materialized_at IS NULL) pending_materialize,
          count(*) FILTER (WHERE materialized_at IS NOT NULL) materialized,
          count(*) FILTER (WHERE status='failed') failed FROM archive_compute_jobs""")
        await tg_send(session,chat_id,
          f"Archive compute: queued={int(s['queued'] or 0)} running={int(s['running'] or 0)} "
          f"pending-materialize={int(s['pending_materialize'] or 0)} "
          f"materialized={int(s['materialized'] or 0)} failed={int(s['failed'] or 0)}")
    elif cmd=="/compute":
        rows=await db.pool.fetch("""SELECT job_type,status,count(*) n FROM ml_jobs
          GROUP BY job_type,status ORDER BY job_type,status""")
        await tg_send(session,chat_id,"Compute jobs:\n"+("\n".join(
          f"{r['job_type']} {r['status']}: {r['n']}" for r in rows) if rows else "none"))
    elif cmd=="/lifecycle":
        rows=await db.pool.fetch("""SELECT state,count(*) n FROM node_lifecycle GROUP BY state ORDER BY state""")
        await tg_send(session,chat_id,"Node lifecycle:\n"+("\n".join(
          f"{r['state']}: {r['n']}" for r in rows) if rows else "none"))
    elif cmd=="/status":
        if len(parts)==1:
            online=sum(1 for n in nodes.values() if now-float(n.get("last_seen",0))<settings.heartbeat_seconds*3)
            await tg_send(session,chat_id,f"Nodes: {len(nodes)}, online: {online}, offline: {len(nodes)-online}")
        else:
            nid=parts[1]
            n=nodes.get(nid)
            await tg_send(session,chat_id,_node_line(nid,n,now) if n else f"Unknown node: {nid}")
    elif cmd in ("/pause","/resume","/stop","/start","/restart","/rollback"):
        if cmd in ("/resume","/start"):
            gs=await runtime_state(db.pool)
            if gs["state"]!="ACTIVE":
                await tg_send(session,chat_id,f"Blocked: global SYSTEM state is {gs['state']}. Use ПРОДОЛЖИТЬ for the whole Grid first.")
                return
        if len(parts)!=2:
            await tg_send(session,chat_id,f"Usage: {cmd} NODE")
            return
        cid=await enqueue_command(db.pool,parts[1],cmd[1:],{})
        await tg_send(session,chat_id,f"{cmd[1:]} queued for {parts[1]} ({cid})")
    elif cmd=="/update":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /update VERSION")
            return
        version=parts[1]
        canary=_healthy_canary(nodes)
        if not canary:
            await tg_send(session,chat_id,"No healthy online node available for canary.")
            return
        try:
            rel=await start_canary(db.pool,version,canary,3)
        except ValueError as e:
            await tg_send(session,chat_id,f"Update rejected: {e}")
            return
        cid=await enqueue_command(db.pool,canary,"update",rel)
        await tg_send(session,chat_id,f"Canary update {version} queued for {canary} ({cid}). Waiting for 3 healthy heartbeats.")
    elif cmd=="/rollout":
        rows=await db.pool.fetch("""SELECT version,phase,status,canary_node,required_health_acks,last_error
                                  FROM rollout_state ORDER BY created_at DESC LIMIT 5""")
        if not rows:
            await tg_send(session,chat_id,"No rollout history.")
        else:
            lines=["Recent rollouts:"]
            for r in rows:
                lines.append(f"{r['version']}: {r['phase']} / {r['status']}, canary={r['canary_node']}, error={r['last_error'] or '-'}")
            await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/errors":
        rows=await db.pool.fetch("""SELECT node_id,action,status,error,created_at FROM agent_commands
                                  WHERE status='failed' ORDER BY created_at DESC LIMIT 10""")
        lines=["Recent command errors:"]
        lines += [f"{r['node_id']} {r['action']}: {r['error'] or 'failed'}" for r in rows]
        await tg_send(session,chat_id,"\n".join(lines) if rows else "No recent command errors.")
    elif cmd=="/logs":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /logs NODE")
            return
        nid=parts[1]
        if nid not in nodes:
            await tg_send(session,chat_id,f"Unknown node: {nid}")
            return
        cid=await enqueue_command(db.pool,nid,"log_tail",{"lines":120})
        await tg_send(session,chat_id,f"Log tail requested from {nid} ({cid}). Use /logresult {cid} in a few seconds.")
    elif cmd=="/logresult":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /logresult COMMAND_ID")
            return
        try:
            row=await db.pool.fetchrow("""SELECT node_id,status,result,error FROM agent_commands
                WHERE id=$1::uuid AND action='log_tail'""",parts[1])
        except Exception:
            row=None
        if not row:
            await tg_send(session,chat_id,"Unknown log request.")
        elif row["status"]!="done":
            await tg_send(session,chat_id,f"{row['node_id']}: {row['status']} {row['error'] or ''}".strip())
        else:
            result=_decode_command_result(row["result"])
            lines=result.get("lines",[])
            body="\n".join(lines[-80:])
            await tg_send(session,chat_id,body or result.get("message","No log lines."))
    elif cmd=="/uninstall":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /uninstall NODE")
            return
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("uninstall",parts[1],time.time()+120)
        await tg_send(session,chat_id,f"Confirm uninstall of {parts[1]} within 120s: /confirm {code}")
    elif cmd=="/cleanupplan":
        lines=["Retention dry-run:"]
        for dataset,days in RETENTION_DEFAULTS.items():
            p=await cleanup_plan(db.pool,dataset,days)
            lines.append(f"{dataset}: deletable={p['deletable']} blocked={p.get('blocked') or '-'}")
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/cleanup":
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("cleanup",None,time.time()+120)
        await tg_send(session,chat_id,f"Confirm DB cleanup within 120s: /confirm {code}")
    elif cmd=="/confirm":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /confirm CODE")
            return
        key=(str(chat_id),parts[1].upper())
        item=_pending_confirms.pop(key,None)
        if not item or item[2]<time.time():
            await tg_send(session,chat_id,"Confirmation expired or invalid.")
            return
        action,node_id,_=item
        if action=="uninstall":
            cid=await enqueue_command(db.pool,node_id,"uninstall",{"purge_data":False})
            await tg_send(session,chat_id,f"Uninstall queued for {node_id} ({cid}); data preserved.")
        elif action=="pilot_validate":
            try:
                state=await begin_server_pilot_validation(
                    db.pool,node_id,nodes,settings.heartbeat_seconds
                )
            except ValueError as e:
                await tg_send(session,chat_id,f"Pilot validation rejected: {e}")
                return
            await tg_send(
                session,chat_id,
                f"Pilot {node_id}: {state['mode']} / {state['phase']}, "
                f"progress={float(state['progress']):.1f}%, paused={state['paused']}. "
                "Global runtime remains STOPPED; use the separate fleet lifecycle only when ready."
            )
        elif action=="fleet_begin":
            current=await runtime_state(db.pool)
            if current["state"]!="INFRA_ONLY":
                await tg_send(session,chat_id,f"START confirmation rejected: SYSTEM state changed to {current['state']}.",_main_keyboard())
                return
            readiness=await start_readiness(db.pool,nodes,settings.heartbeat_seconds)
            if not readiness["ready"]:
                await tg_send(session,chat_id,"START confirmation rejected by readiness gate: "+", ".join(readiness["missing"]),_main_keyboard())
                return
            state=await set_runtime_state(db.pool,"ACTIVE",f"telegram:{chat_id}","explicit operator START after readiness")
            await tg_send(session,chat_id,f"SYSTEM: {state['state']}. Market workloads may now start.",_main_keyboard())
        elif action=="fleet_delete":
            r=await begin_fleet_delete(db.pool,nodes,f"telegram:{chat_id}")
            await tg_send(session,chat_id,f"DELETE operation {r['operation_id']} started for {len(r['targets'])} agents. CONTROL remains online until all agents acknowledge purge. Check: /deletestatus {r['operation_id']}")
        else:
            result=await cleanup_all(db.pool)
            await tg_send(session,chat_id,"Cleanup completed: "+", ".join(f"{k}={v}" for k,v in result.items()))
    elif cmd=="/deletestatus":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /deletestatus OPERATION_ID"); return
        r=await fleet_delete_status(db.pool,parts[1])
        if not r: await tg_send(session,chat_id,"Unknown delete operation.")
        elif r["status"]=="READY_CONTROL_PURGE":
            await tg_send(session,chat_id,"All agent purge commands acknowledged. CONTROL is ready for final local purge.")
        else:
            await tg_send(session,chat_id,"DELETE waiting. Pending: "+(", ".join(r["pending"]) or "-")+"; failed: "+(", ".join(r["failed"]) or "-"))
    elif cmd in ("/db","/dbsize","/storage"):
        st=await database_stats(db.pool)
        lines=[f"DB: {st['database']['name']}","Size: "+str(st["database"]["pretty"]),"Largest tables:"]
        lines += [f"- {t['table_name']}: {t['pretty']}" for t in st["tables"][:8]]
        await tg_send(session,chat_id,"\n".join(lines))
    else:
        await tg_send(session,chat_id,"Commands: /menu /system /joinpilot [LABEL] /joinagent [LABEL] /begin /fleetstop /fleetresume /fleetdelete /pilot /pilot [NODE] /pilotvalidate NODE /health /nodes /node NODE /status [NODE] /update VERSION /rollout /errors /logs NODE /logresult ID /pause NODE /resume NODE /stop NODE /start NODE /restart NODE /rollback NODE /uninstall NODE /cleanupplan /cleanup /db /research [RUN] /archive /compute /lifecycle")

async def _maybe_finalize_fleet_delete(db,session):
    op=await latest_operation(db.pool,"DELETE")
    if not op or op["status"] not in ("WAITING","READY_CONTROL_PURGE"):
        return
    status=await fleet_delete_status(db.pool,str(op["id"]))
    if not status or status["status"]!="READY_CONTROL_PURGE":
        return
    # Mark durably BEFORE spawning the final remover so a Telegram-loop retry cannot
    # launch multiple destructive processes.
    changed=await db.pool.execute("""UPDATE fleet_operations SET status='CONTROL_PURGE_STARTED',
      completed_at=now() WHERE id=$1 AND status='READY_CONTROL_PURGE'""",op["id"])
    if not str(changed).endswith("1"):
        return
    chats=[x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()]
    for chat_id in chats:
        try:
            await tg_send(session,chat_id,"All agents acknowledged deletion. CONTROL and Grid-owned PostgreSQL/data are now being removed. This bot will go offline when deletion completes.")
        except Exception:
            pass
    data_root=pathlib.Path(os.environ.get("ProgramData",r"C:\\ProgramData"))/"BybitClusterGrid"
    script=data_root/"installer"/"uninstall.ps1"
    if not script.exists():
        await db.pool.execute("UPDATE fleet_operations SET status='FAILED',details=details || $2::jsonb WHERE id=$1",
                              op["id"],'{"control_error":"local uninstall script missing"}')
        return
    subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script),"-PurgeData"],
                     creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

async def _notify_expansion_ready(db,session):
    rows=await expansion_ready(db.pool)
    chats=[x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()]
    if not chats:return
    for r in rows:
        if r.get("expansion_notified_at") is not None: continue
        message=f"Pilot {r['node_id']} completed bootstrap and live validation. Grid is READY_FOR_EXPANSION; other agents may now be installed."
        sent=False
        for chat_id in chats:
            try:
                await tg_send(session,chat_id,message); sent=True
            except Exception:
                log.exception("pilot readiness notification failed",extra={"event":"pilot_notify_failed"})
        if sent: await mark_expansion_notified(db.pool,r["node_id"])

async def telegram_loop(db,nodes):
    if not settings.telegram_bot_token:
        log.info("telegram disabled",extra={"event":"telegram_disabled"})
        return
    if not settings.telegram_allowed_chat_ids.strip():
        log.error("telegram disabled: allowlist is empty",extra={"event":"telegram_no_allowlist"})
        return
    offset=await telegram_cursor(db.pool)
    node_id=getattr(db,'node_id','telegram-leader')
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
                async with session.get(url,params={"timeout":30,"offset":offset},timeout=40) as r:
                    data=await r.json(content_type=None)
                    if r.status!=200 or not bool(data.get("ok")):
                        raise RuntimeError(f"Telegram getUpdates failed status={r.status}: {str(data)[:500]}")
                op_result=await reconcile_fleet_operation(db.pool)
                if op_result and op_result.get("status")=="DONE":
                    for notify_chat in [x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()]:
                        try: await tg_send(session,notify_chat,f"SYSTEM: {op_result['state']}. Global {op_result['action']} acknowledged by all required agents.",_main_keyboard())
                        except Exception: pass
                await _notify_expansion_ready(db,session)
                await _maybe_finalize_fleet_delete(db,session)
                for upd in data.get("result",[]):
                    next_offset=max(offset,upd["update_id"]+1)
                    cb=upd.get("callback_query") or {}
                    msg=upd.get("message") or cb.get("message") or {}
                    chat=(msg.get("chat") or {}).get("id")
                    txt=msg.get("text","")
                    if cb:
                        mapping={"fleet:begin":"/begin","fleet:stop":"/fleetstop","fleet:resume":"/fleetresume","fleet:delete":"/fleetdelete","fleet:nodes":"/nodes","fleet:system":"/system","fleet:menu":"/menu","fleet:research":"/research","fleet:archive":"/archive","fleet:storage":"/db","fleet:errors":"/errors"}
                        callback_data=cb.get("data") or ""
                        txt=mapping.get(callback_data,"")
                        if callback_data.startswith("node:"):
                            p=callback_data.split(":",2)
                            if len(p)==3:
                                action,nid=p[1],p[2]
                                cmdmap={"show":"/node","pause":"/pause","resume":"/resume","stop":"/stop","start":"/start","restart":"/restart","logs":"/logs","uninstall":"/uninstall"}
                                if action in cmdmap: txt=cmdmap[action]+" "+nid
                        try:
                            async with session.post(
                                f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",
                                json={"callback_query_id":cb.get("id")},timeout=10) as ar:
                                await ar.read()
                        except Exception:
                            pass
                    if not chat or not txt.startswith("/"):
                        offset=await commit_telegram_cursor(db.pool,node_id,next_offset); continue
                    if not allowed(chat):
                        log.warning("telegram unauthorized",extra={"event":"telegram_denied"})
                        offset=await commit_telegram_cursor(db.pool,node_id,next_offset); continue
                    claimed=await claim_update(db.pool,upd["update_id"],chat,txt,node_id)
                    if not claimed:
                        offset=await commit_telegram_cursor(db.pool,node_id,next_offset); continue
                    try:
                        await handle_command(db,session,chat,txt,nodes)
                        await complete_update(db.pool,upd["update_id"])
                    except Exception as e:
                        await complete_update(db.pool,upd["update_id"],str(e)[:500])
                        raise
                    await _notify_expansion_ready(db,session)
                    offset=await commit_telegram_cursor(db.pool,node_id,next_offset)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("telegram loop failed",extra={"event":"telegram_error"})
                await asyncio.sleep(5)
