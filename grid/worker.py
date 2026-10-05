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
from .micro_event_storage import MicroEventStorage
from .micro_tape import MicroTapeAggregator
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
from .local_control_journal import LocalControlJournal
from .control_snapshot_ring import ControlSnapshotRing,replica_meta
from .integrity_guard import verify_manifest
from .command_receipts import CommandReceiptStore

log=logging.getLogger("worker")

class Worker:
    def __init__(self):
        self.wanted=set()
        self.trade_tasks={}
        self.micro_tasks=[]
        self.micro_signature=()
        self.micro_wanted=set()
        self.storage=Storage()
        self.micro_storage=MicroEventStorage()
        self.micro_tape=MicroTapeAggregator(settings.micro_tape_bucket_ms)
        self.db=None
        self.meta={}
        self.enabled=True
        self.bootstrap_paused=False
        self.operator_stopped=False
        self.bootstrap_phase=os.getenv('GRID_BOOTSTRAP_PHASE','NORMAL')
        self.runtime_state='INFRA_ONLY'
        self.pressure=PressureController(settings.resource_cpu_limit,settings.resource_ram_limit,settings.resource_disk_free_gb)
        self.pressure_drained=set()
        self.control_journal=LocalControlJournal(os.getenv('GRID_CONTROL_JOURNAL','control-state.json'))
        self.control_ring=ControlSnapshotRing(os.getenv('GRID_CONTROL_SNAPSHOTS','control-snapshots'))
        self.command_receipts=CommandReceiptStore()

    async def heartbeat(self):
        async with aiohttp.ClientSession() as s:
            while True:
                snap=snapshot()
                try:
                    install_root=os.getenv('GRID_INSTALL_ROOT','.')
                    manifest=os.getenv('GRID_RELEASE_MANIFEST','release-manifest.json')
                    ir=verify_manifest(install_root,manifest) if os.path.exists(manifest) else {'ok':False,'bad':[],'missing':['release-manifest.json'],'version':None}
                    snap.update({'integrity_ok':ir['ok'],'integrity_bad':ir['bad'],'integrity_missing':ir['missing'],'integrity_version':ir.get('version')})
                except Exception as e:
                    snap.update({'integrity_ok':False,'integrity_bad':[],'integrity_missing':['manifest/unreadable'],'integrity_error':str(e)[:300]})
                try: snap.update(replica_meta(self.control_journal))
                except Exception:
                    snap.update({'control_generation':0,'control_checksum':'CORRUPT'})
                dbm=self.storage.metrics()
                microm=self.micro_storage.metrics()
                combined_pressure=max(
                    dbm["queue_ratio"],dbm.get("spool_ratio",0.0),
                    microm["queue_ratio"],microm.get("spool_ratio",0.0),
                )
                state=self.pressure.update(snap,combined_pressure)
                snap.update({"db_queue_depth":dbm["queue_depth"],
                             "db_queue_capacity":dbm["queue_capacity"],
                             "db_queue_ratio":round(dbm["queue_ratio"],4),
                             "db_writes_per_sec":round(dbm["writes_per_sec"],3),
                             "db_write_failures":dbm["write_failures"],
                             "db_spool_bytes":dbm.get("spool_bytes",0),
                             "db_spool_ratio":round(dbm.get("spool_ratio",0.0),4),
                             "db_avg_write_latency_ms":round(dbm["avg_write_latency_ms"],3),
                             "micro_queue_depth":microm["queue_depth"],
                             "micro_queue_capacity":microm["queue_capacity"],
                             "micro_queue_ratio":round(microm["queue_ratio"],4),
                             "micro_write_failures":microm["write_failures"],
                             "micro_spool_bytes":microm.get("spool_bytes",0),
                             "micro_spool_ratio":round(microm.get("spool_ratio",0.0),4)})
                snap['pressure_state']=state
                snap['bootstrap_paused']=self.bootstrap_paused
                snap['operator_stopped']=self.operator_stopped
                snap['bootstrap_phase']=self.bootstrap_phase
                snap['runtime_state']=self.runtime_state
                snap['wanted_symbols']=len(self.wanted)
                snap['active_trade_streams']=sum(1 for t in self.trade_tasks.values() if not t.done())
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
                            replica=reply.get("control_replica")
                            if replica:
                                try:
                                    if self.control_journal.apply(replica["version"],replica["state"]):
                                        self.control_ring.store(replica["version"],replica["state"])
                                except Exception:
                                    log.exception("control replica apply failed",extra={"event":"control_replica_failed"})
                            for cmd in reply.get("commands",[]):
                                ok=True; result=None; error=None
                                receipt=self.command_receipts.get(cmd.get("id"))
                                if receipt is not None:
                                    ok=bool(receipt.get("ok"))
                                    result=receipt.get("result")
                                    error=receipt.get("error")
                                    log.info("replayed durable command receipt",extra={"event":"command_receipt_replay"})
                                else:
                                    try:
                                        result=await execute_command(self,cmd)
                                    except Exception as e:
                                        ok=False; error=str(e)
                                        log.exception("agent command failed",extra={"event":"agent_command_failed"})
                                    # Persist before ACK. If the process/network dies after this point,
                                    # redelivery is acknowledged from the receipt without re-execution.
                                    self.command_receipts.put(cmd.get("id"),ok,result,error)
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
                            self.runtime_state=str(reply.get("runtime_state","INFRA_ONLY"))
                            market_enabled=bool(reply.get("market_work_enabled",False)) and self.runtime_state=="ACTIVE"
                            if market_enabled and not self.meta:
                                try:
                                    self.meta={x["symbol"]:x for x in await linear_symbols(settings.bybit_rest_url)}
                                except Exception:
                                    log.exception("instrument metadata refresh failed",extra={"event":"metadata_refresh_failed"})
                            assigned=set(reply.get("symbols",[])) if self.enabled and market_enabled else set()
                            if state in (NORMAL,SOFT_PRESSURE):
                                self.pressure_drained.clear()
                            else:
                                self.pressure_drained.update(self.pressure.symbols_to_drain(assigned-self.pressure_drained))
                            new=assigned-self.pressure_drained
                            requested_micro=set(reply.get("micro_symbols",[]))
                            new_micro=requested_micro & new
                            if new != self.wanted or new_micro != self.micro_wanted:
                                self.wanted=new
                                self.micro_wanted=new_micro
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

    async def set_operator_stop(self,stopped):
        flag=os.path.join(os.environ.get("ProgramData",r"C:\ProgramData"),"BybitClusterGrid","operator.stop")
        os.makedirs(os.path.dirname(flag),exist_ok=True)
        if stopped:
            with open(flag,"w",encoding="utf-8") as f:f.write("stopped\n")
        else:
            try:os.remove(flag)
            except FileNotFoundError:pass

    async def set_bootstrap_pause(self,paused):
        self.bootstrap_paused=bool(paused)
        flag=os.path.join(os.environ.get("ProgramData",r"C:\ProgramData"),"BybitClusterGrid","bootstrap.pause")
        os.makedirs(os.path.dirname(flag),exist_ok=True)
        if paused:
            with open(flag,"w",encoding="utf-8") as f:f.write("paused\n")
        else:
            try:os.remove(flag)
            except FileNotFoundError:pass

    async def reconcile(self):
        for sym in list(self.trade_tasks):
            if sym not in self.wanted:
                self.trade_tasks.pop(sym).cancel()
        for sym in self.wanted:
            if sym in self.meta and sym not in self.trade_tasks:
                self.trade_tasks[sym]=asyncio.create_task(self.trade_stream(sym))

        signature=tuple(sorted(self.micro_wanted))
        if signature != self.micro_signature:
            self.micro_signature=signature
            for t in self.micro_tasks:
                t.cancel()
            if self.micro_tasks:
                await asyncio.gather(*self.micro_tasks,return_exceptions=True)
            self.micro_tasks=[]
            collector=MicrostructureCollector(
                self.micro_storage,
                snapshot_ms=settings.microstructure_snapshot_ms,
            )
            symbols=list(signature)
            for i in range(0,len(symbols),8):
                batch=symbols[i:i+8]
                if batch:
                    self.micro_tasks.append(asyncio.create_task(collector.run_batch(batch)))
            log.info("microstructure assignment reconciled",extra={"event":"micro_assignment","component":f"{len(symbols)} symbols"})

    async def trade_stream(self,symbol):
        tick=self.meta[symbol]["tick_size"]
        fp=FootprintBuilder(tick,settings.cluster_interval_seconds,finalization_delay_ms=2000)
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
                    # A TCP/WebSocket connection is not enough: fail closed unless
                    # Bybit explicitly accepted the market subscription.
                    while True:
                        raw=await asyncio.wait_for(ws.recv(),timeout=15)
                        ack=json.loads(raw)
                        if ack.get("op")=="subscribe":
                            if ack.get("success") is not True:
                                raise RuntimeError("Bybit trade subscription rejected: "+str(ack.get("ret_msg") or ack))
                            break
                    if connected_once:
                        continuity.reconnect()
                        fp.mark_open_degraded(symbol,"ws_reconnect")
                    connected_once=True
                    delays=backoff_delays()
                    while True:
                        raw=await asyncio.wait_for(ws.recv(),timeout=45)
                        msg=json.loads(raw)
                        if not msg.get("topic","").startswith("publicTrade."):
                            continue
                        batch=msg.get("data",[])
                        self.pressure.observe_symbol(symbol,events=len(batch))
                        for x in batch:
                            trade_ts=int(x["T"])
                            suspect_gap=continuity.observe(trade_ts)
                            trade=Trade(
                                symbol=symbol,
                                ts_ms=trade_ts,
                                price=float(x["p"]),
                                qty=float(x["v"]),
                                side=x["S"],
                                trade_id=x.get("i","")
                            )
                            fp.add(trade)
                            if symbol in self.micro_wanted:
                                tape_row=self.micro_tape.add(trade)
                                if tape_row is not None:
                                    await self.micro_storage.insert_event(
                                        symbol,
                                        tape_row["start_ms"],
                                        "trade_tape_250ms",
                                        tape_row,
                                    )
                            if suspect_gap:
                                fp.mark_degraded(symbol,trade_ts,"trade_time_gap")
                        for row in fp.pop_closed(int(time.time()*1000)):
                            await self.storage.save(row)
                            self.pressure.observe_symbol(symbol,db_writes=1)
            except asyncio.CancelledError:
                raise
            except BufferError:
                self.pressure.state="CRITICAL"
                self.pressure.bad_ticks=max(self.pressure.bad_ticks,10)
                log.error("local WAL pressure; draining live symbols until database catches up",
                          extra={"event":"wal_pressure","symbol":symbol})
                await asyncio.sleep(max(5,settings.heartbeat_seconds))
            except Exception:
                d=next(delays)
                log.exception("trade stream failed",extra={
                    "event":"reconnect","symbol":symbol,"delay":d
                })
                await asyncio.sleep(d)

    async def run(self):
        bootstrap_logging()
        # Workers are DB-less by design: CONTROL owns PostgreSQL and accepts
        # authenticated ingestion. This keeps database credentials off agent PCs.
        self.db=None
        await self.storage.start()
        await self.micro_storage.start()
        # Strict INFRA_ONLY: no Bybit discovery is permitted before CONTROL opens ACTIVE.
        self.meta={}
        stop_flag=os.path.join(os.environ.get("ProgramData",r"C:\ProgramData"),"BybitClusterGrid","operator.stop")
        if os.path.exists(stop_flag):
            self.operator_stopped=True; self.enabled=False

        health_task=asyncio.create_task(health_monitor())
        # Retention, strategy orchestration and Telegram are CONTROL-owned.
        try:
            await self.heartbeat()
        finally:
            # Stop producers first, then give durable sinks a bounded chance to
            # flush. Anything left stays in WAL and is replayed after restart.
            for task in list(self.trade_tasks.values())+list(self.micro_tasks):
                task.cancel()
            await asyncio.gather(*list(self.trade_tasks.values()),*self.micro_tasks,return_exceptions=True)
            health_task.cancel()
            await asyncio.gather(health_task,return_exceptions=True)
            await self.micro_storage.close()
            await self.storage.close()

async def main():
    await Worker().run()

if __name__=="__main__":
    asyncio.run(main())
