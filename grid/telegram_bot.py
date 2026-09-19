import asyncio, logging
import aiohttp
from .config import settings
from .db_stats import database_stats
from .retention import cleanup_all

log=logging.getLogger("telegram")

def allowed(chat_id):
    raw=[x.strip() for x in settings.telegram_allowed_chat_ids.split(",") if x.strip()]
    return not raw or str(chat_id) in raw

async def tg_send(session,chat_id,text):
    url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    await session.post(url,json={"chat_id":chat_id,"text":text[:4000]})

def fmt_bytes(n):
    if n is None: return "n/a"
    units=["B","KB","MB","GB","TB"]
    x=float(n)
    for u in units:
        if x<1024 or u==units[-1]: return f"{x:.2f} {u}"
        x/=1024

async def handle_command(db,session,chat_id,text):
    cmd=text.strip().split()[0].lower()
    if cmd in ("/db","/dbsize","/storage"):
        s=await database_stats(db.pool)
        lines=[
            f"DB: {s['database']['name']}",
            f"Size: {s['database']['pretty']}",
            "Largest tables:",
        ]
        for t in s["tables"][:8]:
            lines.append(f"- {t['table_name']}: {t['pretty']}")
        lines.append("Rows:")
        for k,v in s["counts"].items():
            lines.append(f"- {k}: {v}")
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/cleanup":
        await tg_send(session,chat_id,"Cleanup started.")
        result=await cleanup_all(db.pool)
        lines=["Cleanup completed:"]+[f"- {k}: {v} rows" for k,v in result.items()]
        await tg_send(session,chat_id,"\n".join(lines))
    elif cmd=="/retention":
        s=await database_stats(db.pool)
        lines=["Analysis watermarks:"]
        if not s["watermarks"]:
            lines.append("- none: cleanup will not delete analyzed datasets yet")
        else:
            for w in s["watermarks"]:
                lines.append(f"- {w['dataset']}: {w['symbols']} symbols, {w['min_watermark']} .. {w['max_watermark']}")
        await tg_send(session,chat_id,"\n".join(lines))

async def telegram_loop(db):
    if not settings.telegram_bot_token:
        log.info("telegram disabled",extra={"event":"telegram_disabled"})
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
                    text=msg.get("text","")
                    if not chat or not text.startswith("/"): continue
                    if not allowed(chat):
                        log.warning("telegram unauthorized",extra={"event":"telegram_denied"})
                        continue
                    await handle_command(db,session,chat,text)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("telegram loop failed",extra={"event":"telegram_error"})
                await asyncio.sleep(5)
