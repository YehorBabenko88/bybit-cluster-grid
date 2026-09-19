import asyncio, json, time, logging, os
import aiohttp, websockets
from .config import settings
from .resources import snapshot
from .models import Trade
from .cluster import FootprintBuilder
from .storage import Storage
from .bybit import linear_symbols
from .service import prepare_database, bootstrap_logging, health_monitor
from .microstructure import MicrostructureCollector
from .resilience import backoff_delays, wait_for_internet
from .retention import ensure_retention_schema, retention_scheduler
from .telegram_bot import telegram_loop
from .strategy_jobs import ensure_strategy_schema
from .strategy_plugins import ensure_plugin_schema
from .strategy_runner import strategy_worker
from .agent_commands import execute_command
from .credential_store import node_credential
from .decommission import mark_coordinator_success,mark_internet_success,internet_available,decommission_due
from .pressure import PressureController, NORMAL, SOFT_PRESSURE
from .continuity import TradeContinuity

log=logging.getLogger("worker")

class Worker:
    def __init__(self):
        self.wanted=set()
        self.trade_tasks={}
        self.micro_tasks=[]
        self.micro_signature=()
        self.storage=Storage()
        self.db=None
        self.meta={}
        self.enabled=True
        self.pressure=PressureController(settings.resource_cpu_limit,settings.resource_ram_limit,settings.resource_disk_free_gb)
        self.pressure_drained=set()

    async def heartbeat(self):
        async with aiohttp.ClientSession() as s:
            while True:
                snap=snapshot()
                dbm=self.storage.metrics()
                state=self.pressure.update(snap,max(dbm["queue_ratio"],dbm.get("spool_ratio",0.0)))
                snap.update({"db_queue_depth":dbm["queue_depth"],
                             "db_queue_capacity":dbm["queue_capacity"],
                             "db_queue_ratio":round(dbm["queue_ratio"],4),
                             "db_writes_per_sec":round(dbm["writes_per_sec"],3),
                             "db_write_failures":dbm["write_failures"],
                             "db_spool_bytes":dbm.get("spool_bytes",0),
                             "db_spool_ratio":round(dbm.get("spool_ratio",0.0),4),
                             "db_avg_write_latency_ms":round(dbm["avg_write_latency_ms"],3)})
                snap['pressure_state']=state
                snap['pressure_drained']=len(self.pressure_drained)
                snap['drained_symbols']=sorted(self.pressure_drained)
                snap['symbol_cost']={k:round(v,3) for k,v in self.pressure.symbol_cost.items() if k in self.wanted}
                try:
                    async with s.post(
                        settings.coordinator_url+"/heartbeat",
                        json=snap,
                        headers={
                            "X-Grid-Token":settings.grid_shared_token,
                            "X-Node-Credential":node_credential(),
                        },
                        timeout=10
                    ) as r:
                        if r.status==200:
                            mark_coordinator_success()
                            reply=await r.json()
                            for cmd in reply.get("commands",[]):
                                ok=True; result=None; error=None
                                try:
                                    result=await execute_command(self,cmd)
                                except Exception as e:
                                    ok=False; error=str(e)
                                    log.exception("agent command failed",extra={"event":"agent_command_failed"})
                                try:
                                    await s.post(
                                        settings.coordinator_url+f"/commands/{cmd['id']}/result",
                                        json={"node_id":snap["node_id"],"ok":ok,"result":result,"error":error},
                                        headers={
                                            "X-Grid-Token":settings.grid_shared_token,
                                            "X-Node-Credential":node_credential(),
                                        },timeout=10
                                    )
                                except Exception:
                                    log.exception("command acknowledgement failed",extra={"event":"command_ack_failed"})
                            assigned=set(reply.get("symbols",[])) if self.enabled else set()
                            if state in (NORMAL,SOFT_PRESSURE):
                                self.pressure_drained.clear()
                            else:
                                self.pressure_drained.update(self.pressure.symbols_to_drain(assigned-self.pressure_drained))
                            new=assigned-self.pressure_drained
                            if new != self.wanted:
                                self.wanted=new
                                await self.reconcile()
                        else:
                            log.warning("coordinator heartbeat rejected",extra={"event":"heartbeat_rejected"})
                except Exception:
                    log.exception("heartbeat failed",extra={"event":"heartbeat_failed"})
                    if internet_available():
                        mark_internet_success()
                    elif decommission_due(settings.decommission_days):
                        log.critical("offline decommission threshold reached",extra={"event":"self_decommission"})
                        try:
                            await execute_command(self,{"action":"uninstall","payload":{"purge_data":True}})
                        finally:
                            os._exit(0)
                await asyncio.sleep(settings.heartbeat_seconds)

    async def reconcile(self):
        for sym in list(self.trade_tasks):
            if sym not in self.wanted:
                self.trade_tasks.pop(sym).cancel()
        for sym in self.wanted:
            if sym in self.meta and sym not in self.trade_tasks:
                self.trade_tasks[sym]=asyncio.create_task(self.trade_stream(sym))

        signature=tuple(sorted(self.wanted))
        if signature != self.micro_signature:
            self.micro_signature=signature
            for t in self.micro_tasks:
                t.cancel()
            if self.micro_tasks:
                await asyncio.gather(*self.micro_tasks,return_exceptions=True)
            self.micro_tasks=[]
            collector=MicrostructureCollector(self.db,snapshot_ms=1000)
            symbols=list(signature)
            for i in range(0,len(symbols),8):
                batch=symbols[i:i+8]
                if batch:
                    self.micro_tasks.append(asyncio.create_task(collector.run_batch(batch)))
            log.info("assignment reconciled",extra={"event":"assignment","component":f"{len(symbols)} symbols"})

    async def trade_stream(self,symbol):
        tick=self.meta[symbol]["tick_size"]
        fp=FootprintBuilder(tick,settings.cluster_interval_seconds)
        delays=backoff_delays()
        continuity=TradeContinuity(gap_ms=max(5000,settings.cluster_interval_seconds*1000//2))
        connected_once=False
        while True:
            try:
                await wait_for_internet()
                async with websockets.connect(
                    settings.bybit_ws_url,
                    ping_interval=20,ping_timeout=20,max_queue=50000,close_timeout=5
                ) as ws:
                    await ws.send(json.dumps({"op":"subscribe","args":[f"publicTrade.{symbol}"]}))
                    if connected_once:
                        continuity.reconnect()
                        fp.mark_open_degraded(symbol,"ws_reconnect")
                    connected_once=True
                    delays=backoff_delays()
                    async for raw in ws:
                        msg=json.loads(raw)
                        batch=msg.get("data",[])
                        self.pressure.observe_symbol(symbol,events=len(batch))
                        for x in batch:
                            trade_ts=int(x["T"])
                            suspect_gap=continuity.observe(trade_ts)
                            fp.add(Trade(
                                symbol=symbol,
                                ts_ms=trade_ts,
                                price=float(x["p"]),
                                qty=float(x["v"]),
                                side=x["S"],
                                trade_id=x.get("i","")
                            ))
                            if suspect_gap:
                                fp.mark_degraded(symbol,trade_ts,"trade_time_gap")
                        for row in fp.pop_closed(int(time.time()*1000)):
                            await self.storage.save(row)
                            self.pressure.observe_symbol(symbol,db_writes=1)
            except asyncio.CancelledError:
                raise
            except Exception:
                d=next(delays)
                log.exception("trade stream failed",extra={
                    "event":"reconnect","symbol":symbol,"delay":d
                })
                await asyncio.sleep(d)

    async def run(self):
        bootstrap_logging()
        self.db=await prepare_database()
        await ensure_retention_schema(self.db.pool)
        await ensure_strategy_schema(self.db.pool)
        await ensure_plugin_schema(self.db.pool)
        await self.storage.start()
        self.meta={x["symbol"]:x for x in await linear_symbols(settings.bybit_rest_url)}

        asyncio.create_task(health_monitor())
        asyncio.create_task(retention_scheduler(self.db.pool,settings))
        # Strategy runner is independent from live collection and needs no agent restart.
        asyncio.create_task(strategy_worker(self.db))
        # Telegram will move to coordinator-only control plane; keep disabled on workers in production.

        await self.heartbeat()

async def main():
    await Worker().run()

if __name__=="__main__":
    asyncio.run(main())
