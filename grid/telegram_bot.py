import asyncio, logging, secrets, time, os, pathlib, subprocess
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
from .fleet_control import fleet_stop,fleet_resume,begin_fleet_delete,fleet_delete_status

log=logging.getLogger("telegram")
_pending_confirms={}

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
      [{"text":"🖥 АГЕНТЫ","callback_data":"fleet:nodes"},{"text":"ℹ СОСТОЯНИЕ","callback_data":"fleet:system"}]
    ]}

async def tg_send(session,chat_id,text,reply_markup=None):
    url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    body={"chat_id":chat_id,"text":text[:4000]}
    if reply_markup: body["reply_markup"]=reply_markup
    await session.post(url,json=body)

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

async def handle_command(db,session,chat_id,text,nodes):
    parts=text.strip().split()
    cmd=parts[0].lower()
    now=time.time()
    if cmd=="/menu":
        await tg_send(session,chat_id,"Управление Bybit Cluster Grid",_main_keyboard())
    elif cmd=="/system":
        s=await runtime_state(db.pool)
        online=sum(1 for n in nodes.values() if now-float(n.get("last_seen",0))<settings.heartbeat_seconds*3)
        await tg_send(session,chat_id,f"SYSTEM: {s['state']}\nNodes: {len(nodes)}, online: {online}\nMarket data: {'ENABLED' if s['state']=='ACTIVE' else 'LOCKED'}\nReason: {s.get('reason') or '-'}")
    elif cmd=="/begin":
        s=await runtime_state(db.pool)
        if s["state"]=="ACTIVE":
            await tg_send(session,chat_id,"System is already ACTIVE.")
            return
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("fleet_begin",None,time.time()+120)
        await tg_send(session,chat_id,"START will enable Bybit discovery, market collection, archive/backfill, feature generation, simulations and learning for the whole Grid.\nConfirm within 120s: /confirm "+code)
    elif cmd in ("/fleetpause","/fleetstop"):
        r=await fleet_stop(db.pool,nodes,f"telegram:{chat_id}")
        await tg_send(session,chat_id,f"SYSTEM: STOPPED. Workloads stopped on {len(r.get('commands',[]))} agents. Control heartbeat remains online so ПРОДОЛЖИТЬ can reach them.",_main_keyboard())
    elif cmd=="/fleetresume":
        r=await fleet_resume(db.pool,nodes,f"telegram:{chat_id}")
        kept=r.get("preserved_stopped") or []
        msg=f"SYSTEM: ACTIVE. Resume queued for {len(r.get('commands',[]))} agents."
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
            result=row["result"] or {}
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
        elif action=="fleet_begin":
            state=await set_runtime_state(db.pool,"ACTIVE",f"telegram:{chat_id}","explicit operator START")
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
        await tg_send(session,chat_id,"Commands: /menu /system /begin /fleetstop /fleetresume /fleetdelete /pilot /pilot [NODE] /health /nodes /node NODE /status [NODE] /update VERSION /rollout /errors /logs NODE /logresult ID /pause NODE /resume NODE /stop NODE /start NODE /restart NODE /rollback NODE /uninstall NODE /cleanupplan /cleanup /db")

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
                    data=await r.json()
                await _notify_expansion_ready(db,session)
                for upd in data.get("result",[]):
                    next_offset=max(offset,upd["update_id"]+1)
                    cb=upd.get("callback_query") or {}
                    msg=upd.get("message") or cb.get("message") or {}
                    chat=(msg.get("chat") or {}).get("id")
                    txt=msg.get("text","")
                    if cb:
                        mapping={"fleet:begin":"/begin","fleet:stop":"/fleetstop","fleet:resume":"/fleetresume","fleet:delete":"/fleetdelete","fleet:nodes":"/nodes","fleet:system":"/system","fleet:menu":"/menu"}
                        data=cb.get("data") or ""
                        txt=mapping.get(data,"")
                        if data.startswith("node:"):
                            p=data.split(":",2)
                            if len(p)==3:
                                action,nid=p[1],p[2]
                                cmdmap={"show":"/node","pause":"/pause","resume":"/resume","stop":"/stop","start":"/start","restart":"/restart","logs":"/logs","uninstall":"/uninstall"}
                                if action in cmdmap: txt=cmdmap[action]+" "+nid
                        try:
                            await session.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",json={"callback_query_id":cb.get("id")})
                        except Exception: pass
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
