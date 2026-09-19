import asyncio, logging, secrets, time
import aiohttp
from .config import settings
from .control_plane import enqueue_command
from .db_stats import database_stats
from .retention import cleanup_all

log=logging.getLogger("telegram")
_pending_confirms={}

def allowed(chat_id):
    raw={x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()}
    return bool(raw) and str(chat_id) in raw

async def tg_send(session,chat_id,text):
    url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    await session.post(url,json={"chat_id":chat_id,"text":text[:4000]})

def _node_line(nid,n,now):
    age=max(0,int(now-float(n.get("last_seen",0))))
    state="ONLINE" if age < settings.heartbeat_seconds*3 else "OFFLINE"
    return f"{nid}: {state}, v={n.get('agent_version','?')}, cpu={n.get('cpu_percent','?')}%, ram={n.get('ram_percent','?')}%, seen={age}s"

async def handle_command(db,session,chat_id,text,nodes):
    parts=text.strip().split()
    cmd=parts[0].lower()
    now=time.time()
    if cmd=="/nodes":
        lines=["Grid nodes:"]+[_node_line(nid,n,now) for nid,n in sorted(nodes.items())]
        await tg_send(session,chat_id,"\n".join(lines) if len(lines)>1 else "No nodes registered.")
    elif cmd=="/status":
        if len(parts)==1:
            online=sum(1 for n in nodes.values() if now-float(n.get("last_seen",0))<settings.heartbeat_seconds*3)
            await tg_send(session,chat_id,f"Nodes: {len(nodes)}, online: {online}, offline: {len(nodes)-online}")
        else:
            nid=parts[1]
            n=nodes.get(nid)
            await tg_send(session,chat_id,_node_line(nid,n,now) if n else f"Unknown node: {nid}")
    elif cmd in ("/pause","/resume","/restart","/rollback"):
        if len(parts)!=2:
            await tg_send(session,chat_id,f"Usage: {cmd} NODE")
            return
        cid=await enqueue_command(db.pool,parts[1],cmd[1:],{})
        await tg_send(session,chat_id,f"{cmd[1:]} queued for {parts[1]} ({cid})")
    elif cmd=="/uninstall":
        if len(parts)!=2:
            await tg_send(session,chat_id,"Usage: /uninstall NODE")
            return
        code=secrets.token_hex(3).upper()
        _pending_confirms[(str(chat_id),code)]=("uninstall",parts[1],time.time()+120)
        await tg_send(session,chat_id,f"Confirm uninstall of {parts[1]} within 120s: /confirm {code}")
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
        else:
            result=await cleanup_all(db.pool)
            await tg_send(session,chat_id,"Cleanup completed: "+", ".join(f"{k}={v}" for k,v in result.items()))
    elif cmd in ("/db","/dbsize","/storage"):
        st=await database_stats(db.pool)
        lines=[f"DB: {st['database']['name']}","Size: "+str(st["database"]["pretty"]),"Largest tables:"]
        lines += [f"- {t['table_name']}: {t['pretty']}" for t in st["tables"][:8]]
        await tg_send(session,chat_id,"\n".join(lines))
    else:
        await tg_send(session,chat_id,"Commands: /nodes /status [NODE] /pause NODE /resume NODE /restart NODE /rollback NODE /uninstall NODE /cleanup /db")

async def telegram_loop(db,nodes):
    if not settings.telegram_bot_token:
        log.info("telegram disabled",extra={"event":"telegram_disabled"})
        return
    if not settings.telegram_allowed_chat_ids.strip():
        log.error("telegram disabled: allowlist is empty",extra={"event":"telegram_no_allowlist"})
        return
    offset=0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
                async with session.get(url,params={"timeout":30,"offset":offset},timeout=40) as r:
                    data=await r.json()
                for upd in data.get("result",[]):
                    offset=max(offset,upd["update_id"]+1)
                    msg=upd.get("message") or {}
                    chat=(msg.get("chat") or {}).get("id")
                    txt=msg.get("text","")
                    if not chat or not txt.startswith("/"): continue
                    if not allowed(chat):
                        log.warning("telegram unauthorized",extra={"event":"telegram_denied"})
                        continue
                    await handle_command(db,session,chat,txt,nodes)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("telegram loop failed",extra={"event":"telegram_error"})
                await asyncio.sleep(5)
