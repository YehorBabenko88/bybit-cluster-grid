import os
import asyncio, json, time, logging, os, pathlib
from .models import Trade
from collections import deque
from .public_trade_validation import (decode_frame,parse_trades,MAX_FRAME_BYTES,MAX_ACK_FRAMES,
    MAX_ACK_BYTES,MAX_OPEN_MINUTES,PERSIST_TIMEOUT_SECONDS,validated_tick,preflight_footprint,preflight_tape)
from .continuity import TradeContinuity
from .raw_capture import RawCaptureError, RawCaptureRecorder

COLLECTOR_PROFILE='grid.data-only-collector.v1'
_FULL_DEPENDENCIES_LOADED=False
_LEGACY_GLOBALS=frozenset(('aiohttp','websockets','settings','snapshot','NODE_ID','ml_runtime_ready',
    'FootprintBuilder','Storage','linear_symbols','prepare_database','bootstrap_logging','health_monitor',
    'MicrostructureCollector','MicroEventStorage','MicroTapeAggregator','backoff_delays','wait_for_internet',
    'ensure_retention_schema','retention_scheduler','telegram_loop','ensure_strategy_schema','ensure_plugin_schema',
    'strategy_worker','execute_command','node_credential','mark_coordinator_success','mark_internet_success',
    'internet_available','decommission_due','PressureController','NORMAL','SOFT_PRESSURE','desired_drained_symbols',
    'LocalControlJournal','ControlSnapshotRing','replica_meta','verify_manifest','CommandReceiptStore',
    'MLTransportClient','ml_agent_loop'))


def __getattr__(name):
    # Preserve legacy attribute access/patching without loading unrelated modules
    # for a data-only import. Private/offline callers never request these names.
    if name not in _LEGACY_GLOBALS:raise AttributeError(name)
    _load_full_worker_dependencies()
    return globals()[name]


def _load_full_worker_dependencies():
    """Legacy collaborators are loaded only for the unchanged full workload."""
    global _FULL_DEPENDENCIES_LOADED
    if _FULL_DEPENDENCIES_LOADED:return
    global aiohttp, websockets, settings, snapshot, NODE_ID, ml_runtime_ready
    global FootprintBuilder, Storage, linear_symbols, prepare_database, bootstrap_logging, health_monitor
    global MicrostructureCollector, MicroEventStorage, MicroTapeAggregator, backoff_delays, wait_for_internet
    global ensure_retention_schema, retention_scheduler, telegram_loop, ensure_strategy_schema, ensure_plugin_schema
    global strategy_worker, execute_command, node_credential, mark_coordinator_success, mark_internet_success
    global internet_available, decommission_due, PressureController, NORMAL, SOFT_PRESSURE, desired_drained_symbols
    global LocalControlJournal, ControlSnapshotRing, replica_meta, verify_manifest, CommandReceiptStore
    global MLTransportClient, ml_agent_loop
    import aiohttp, websockets
    from .config import settings
    from .resources import snapshot,NODE_ID,ml_runtime_ready
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
    from .pressure import PressureController, NORMAL, SOFT_PRESSURE, desired_drained_symbols
    from .local_control_journal import LocalControlJournal
    from .control_snapshot_ring import ControlSnapshotRing,replica_meta
    from .integrity_guard import verify_manifest
    from .command_receipts import CommandReceiptStore
    from .ml_transport_client import MLTransportClient
    from .ml_agent_worker import ml_agent_loop
    _FULL_DEPENDENCIES_LOADED=True

log=logging.getLogger("worker")

class Worker:
    def __init__(self,*,data_first_admission=None,raw_capture_factory=None,launch_profile=None):
        if launch_profile is not None and (type(launch_profile) is not str or launch_profile != COLLECTOR_PROFILE):
            raise ValueError('COLLECTOR_PROFILE_INVALID')
        if launch_profile is not None and (not callable(raw_capture_factory) or data_first_admission is not None):
            raise ValueError('COLLECTOR_CONSTRUCTION_INVALID')
        if raw_capture_factory is not None and not callable(raw_capture_factory):
            raise RawCaptureError('RAW_CAPTURE_FACTORY_INVALID')
        self.launch_profile=launch_profile
        self._offline_used=False
        if launch_profile is None:
            _load_full_worker_dependencies()
        self.raw_capture_factory=raw_capture_factory
        self.raw_capture_failure=None
        self.wanted=set()
        self.trade_tasks={}
        self.micro_tasks=[]
        self.micro_signature=()
        self.micro_wanted=set()
        self.storage=Storage() if launch_profile is None else None
        self.micro_storage=MicroEventStorage() if launch_profile is None else None
        self.micro_tape=MicroTapeAggregator(settings.micro_tape_bucket_ms) if launch_profile is None else None
        self.db=None
        self.meta={}
        self.enabled=True
        self.bootstrap_paused=False
        self.operator_stopped=False
        self.bootstrap_phase=os.getenv('GRID_BOOTSTRAP_PHASE','NORMAL')
        self.runtime_state='INFRA_ONLY'
        self.pressure=PressureController(settings.resource_cpu_limit,settings.resource_ram_limit,settings.resource_disk_free_gb) if launch_profile is None else None
        self.pressure_drained=set()
        self.control_journal=LocalControlJournal(os.getenv('GRID_CONTROL_JOURNAL','control-state.json')) if launch_profile is None else None
        self.control_ring=ControlSnapshotRing(os.getenv('GRID_CONTROL_SNAPSHOTS','control-snapshots')) if launch_profile is None else None
        self.command_receipts=CommandReceiptStore() if launch_profile is None else None
        self.data_first_admission=data_first_admission
        self.data_first_launcher=None
        self.data_first_task=None
        if data_first_admission is not None:
            from .data_first_process import DataFirstProcess
            self.data_first_launcher=DataFirstProcess(data_first_admission)
        self.ml_task=None
        self.ml_stop=asyncio.Event()
        self.restart_requested=False
        # A stale CONTROL assignment must not outlive the coordinator's
        # heartbeat expiry window when the network is partitioned.
        self.last_assignment_heartbeat=None
        self.assignment_lock=asyncio.Lock()
        self._pending_trade_rows={}
        self._pending_trade_locks={}
        self._pending_trade_reservations={}
        self._pending_trade_quality={}

    def _require_full_workload(self):
        if getattr(self,'launch_profile',None) is not None:
            raise RuntimeError('COLLECTOR_SOURCE_ADMISSION_REQUIRED')

    def _raw_capture_for(self,symbol,endpoint):
        factory=getattr(self,'raw_capture_factory',None)
        capture=None if factory is None else factory(symbol,endpoint)
        if factory is not None and (not isinstance(capture,RawCaptureRecorder) or not capture.matches(symbol,endpoint)):
            raise RawCaptureError('RAW_CAPTURE_SOURCE_BINDING_INVALID')
        return capture

    async def _record_received_frame(self,raw,capture):
        ref=None if capture is None else await capture.frame(raw)
        return raw,ref

    async def receive_offline(self,frames,*,symbol,endpoint,observed_at_ms):
        """One finite synthetic receive, never provider admission or a run mode.

        Uses the same raw-before-decode hook and existing trade parser. Results
        remain local observations, not publication or a historical checkpoint.
        """
        if self.launch_profile != COLLECTOR_PROFILE:
            raise RuntimeError('COLLECTOR_OFFLINE_PROFILE_REQUIRED')
        if (type(frames) is not tuple or not 1<=len(frames)<=4
                or endpoint!='synthetic://bybit/linear'
                or type(symbol) is not str or symbol!='BTCUSDT'
                or type(observed_at_ms) is not int or not 0<observed_at_ms<2**63):
            raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
        total=0
        for raw in frames:
            if type(raw) not in (str,bytes):raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            if len(raw)>MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            size=len(raw.encode('utf-8')) if type(raw) is str else len(raw)
            if size>MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
            total+=size
        if total>4*MAX_FRAME_BYTES:raise ValueError('COLLECTOR_OFFLINE_INPUT_INVALID')
        if self._offline_used:raise RuntimeError('COLLECTOR_OFFLINE_ALREADY_USED')
        self._offline_used=True
        capture=self._raw_capture_for(symbol,endpoint)
        if capture is None or capture._source_kind!='SYNTHETIC':
            raise RawCaptureError('RAW_CAPTURE_SOURCE_BINDING_INVALID')
        capture.begin_connection()
        batches=[]
        try:
            for raw in frames:
                raw,ref=await self._record_received_frame(raw,capture)
                try:
                    message,_=decode_frame(raw)
                    trades=parse_trades(message,symbol,observed_at_ms)
                except ValueError:
                    await capture.gap('frame_invalid',ref)
                    continue
                await capture.validated(ref,exchange_event_ms=max((t.ts_ms for t in trades),default=None))
                batches.append(tuple(trades))
            await capture.disconnect('normal_stop')
        except BaseException as error:
            self.raw_capture_failure='COLLECTOR_OFFLINE_UNCERTAIN'
            try:
                await capture.disconnect('cancelled' if isinstance(error,asyncio.CancelledError) else 'transport_error')
            except BaseException as cleanup:
                error.add_note('capture disconnect outcome unknown: '+type(cleanup).__name__)
            raise
        return {'batches':tuple(batches),'metrics':capture.metrics()}

    def data_first_capability(self):
        if self.data_first_launcher is None or self.data_first_task is None or self.data_first_task.done():return None
        try:
            if self.data_first_launcher.require_admitted() is not True:return None
            return self.data_first_admission.runtime_capability()
        except Exception:return None

    def _start_data_first_consumer(self):
        if getattr(self,'launch_profile',None) is not None:return
        # A transient first admission failure must not leave an advertised runtime
        # without a consumer. The waiting loop gates every actual claim.
        if self.data_first_launcher is not None and self.data_first_task is None:
            self.data_first_task=asyncio.create_task(self._data_first_loop())

    def _data_first_can_claim(self):
        try:
            return (self.enabled and not self.operator_stopped and not self.bootstrap_paused
                    and self.runtime_state=="ACTIVE" and snapshot().get("disk_pressure_state")=="NORMAL"
                    and self.data_first_capability() is not None)
        except Exception:return False

    async def _data_first_loop(self):
        self._require_full_workload()
        from .ml_transport_client import DataFirstTransportClient
        from .data_first_agent_worker import run_once
        client=DataFirstTransportClient(NODE_ID)
        while not self.ml_stop.is_set():
            if self._data_first_can_claim():
                try:await run_once(client,process_launcher=self.data_first_launcher)
                except asyncio.CancelledError:raise
                except Exception:
                    # Closed diagnostic only; no transport/credential exception text.
                    log.warning("DataFirst invocation stopped",extra={"event":"data_first_stopped"})
                    return
            try:await asyncio.wait_for(self.ml_stop.wait(),timeout=5)
            except asyncio.TimeoutError:pass

    async def expire_stale_assignments(self, now=None):
        """Revoke collectors when CONTROL stops renewing the assignment lease."""
        async with self.assignment_lock:
            if self.last_assignment_heartbeat is None:
                return False
            current=time.monotonic() if now is None else now
            if current-self.last_assignment_heartbeat < max(1.0,3.0*settings.heartbeat_seconds):
                return False
            if not (self.wanted or self.micro_wanted or self.pressure_drained):
                return False
            log.error("CONTROL assignment lease expired; stopping collectors",
                      extra={"event":"assignment_lease_expired"})
            self.wanted=set()
            self.micro_wanted=set()
            # Never retain drained symbols as implicit assignments after
            # CONTROL has stopped renewing the lease.
            self.pressure_drained=set()
            await self.reconcile()
            return True

    async def assignment_watchdog(self):
        while True:
            await self.expire_stale_assignments()
            await asyncio.sleep(max(0.25,min(1.0,settings.heartbeat_seconds/2)))

    async def _apply_local_pressure(self):
        if self.operator_stopped or self.bootstrap_paused:
            return
        async with self.assignment_lock:
            if not (self.wanted or self.pressure_drained):
                return
            assigned=self.wanted | self.pressure_drained
            drained=desired_drained_symbols(self.pressure,assigned)
            # An expired CONTROL lease must never revive collectors locally.
            if self.last_assignment_heartbeat is not None and (
                time.monotonic()-self.last_assignment_heartbeat >= max(1.0,3.0*settings.heartbeat_seconds)
            ):
                drained=set(assigned)
            if drained != self.pressure_drained:
                self.pressure_drained=drained
                self.wanted=assigned-drained
                self.micro_wanted.intersection_update(self.wanted)
                await self.reconcile()

    async def heartbeat(self):
        self._require_full_workload()
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
                             "db_seconds_since_last_failure":dbm.get("seconds_since_last_failure"),
                             "db_spool_bytes":dbm.get("spool_bytes",0),
                             "db_spool_ratio":round(dbm.get("spool_ratio",0.0),4),
                             "db_avg_write_latency_ms":round(dbm["avg_write_latency_ms"],3),
                             "micro_queue_depth":microm["queue_depth"],
                             "micro_queue_capacity":microm["queue_capacity"],
                             "micro_queue_ratio":round(microm["queue_ratio"],4),
                             "micro_write_failures":microm["write_failures"],
                             "micro_seconds_since_last_failure":microm.get("seconds_since_last_failure"),
                             "micro_spool_bytes":microm.get("spool_bytes",0),
                             "micro_spool_ratio":round(microm.get("spool_ratio",0.0),4),
                             "db_replay_active":bool(dbm.get("replay_active",False)),
                             "db_replay_backlog_bytes":int(dbm.get("replay_backlog_bytes",0)),
                             "micro_replay_active":bool(microm.get("replay_active",False)),
                             "micro_replay_backlog_bytes":int(microm.get("replay_backlog_bytes",0))})
                snap['pressure_state']=state
                # Pressure control must remain autonomous when CONTROL is unreachable.
                # Otherwise a long outage can fill the durable WAL while all market
                # producers keep running. Drain expensive live streams locally; a
                # later healthy CONTROL heartbeat will restore assignments once
                # pressure has recovered.
                await self._apply_local_pressure()
                snap['bootstrap_paused']=self.bootstrap_paused
                snap['operator_stopped']=self.operator_stopped
                snap['bootstrap_phase']=self.bootstrap_phase
                snap['runtime_state']=self.runtime_state
                capability=self.data_first_capability()
                if capability is not None:snap['data_first_runtime']=capability
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
                            # Commands and metadata discovery may take longer than an
                            # assignment lease. Do not renew it from an old response.
                            response_received_at=time.monotonic()
                            # DEV/OBSERVER remains manageable and visible but is fail-closed
                            # for market workload even if an older/misconfigured CONTROL
                            # accidentally returns assignments.
                            if str(settings.node_role or "WORKER").strip().upper()=="DEV_OBSERVER":
                                reply["symbols"]=[]
                                reply["micro_symbols"]=[]
                                reply["live_assignments_enabled"]=False
                            replica=reply.get("control_replica")
                            if replica:
                                try:
                                    if self.control_journal.apply(replica["version"],replica["state"]):
                                        self.control_ring.store(replica["version"],replica["state"])
                                except Exception:
                                    log.exception("control replica apply failed",extra={"event":"control_replica_failed"})
                            for cmd in reply.get("commands",[]):
                                # Never execute a command that cannot be durably
                                # deduplicated and acknowledged by CONTROL.
                                if not isinstance(cmd,dict) or not isinstance(cmd.get("id"),str) or not cmd["id"].strip():
                                    log.error("rejecting CONTROL command without valid id",
                                              extra={"event":"invalid_control_command_id"})
                                    continue
                                ok=True; result=None; error=None
                                receipt=self.command_receipts.get(cmd.get("id"))
                                if receipt is not None:
                                    ok=bool(receipt.get("ok"))
                                    result=receipt.get("result")
                                    error=receipt.get("error")
                                    log.info("replayed durable command receipt",extra={"event":"command_receipt_replay"})
                                else:
                                    # A full journal must reject a new command BEFORE
                                    # side effects; otherwise its receipt cannot be persisted.
                                    self.command_receipts.reserve(cmd["id"])
                                    try:
                                        result=await execute_command(self,cmd)
                                    except Exception as e:
                                        ok=False; error=str(e)
                                        log.exception("agent command failed",extra={"event":"agent_command_failed"})
                                    # Persist before ACK. If the process/network dies after this point,
                                    # redelivery is acknowledged from the receipt without re-execution.
                                    self.command_receipts.put(cmd.get("id"),ok,result,error)
                                try:
                                    async with s.post(
                                        settings.coordinator_url+f"/commands/{cmd['id']}/result",
                                        json={"node_id":snap["node_id"],"ok":ok,"result":result,"error":error},
                                        headers={
                                            "X-Grid-Token":settings.grid_shared_token,
                                            "X-Node-Credential":node_credential(),
                                        },timeout=10
                                    ) as ack_response:
                                        ack_response.raise_for_status()
                                except Exception:
                                    log.exception("command acknowledgement failed",extra={"event":"command_ack_failed"})
                            self.runtime_state=str(reply.get("runtime_state","INFRA_ONLY"))
                            market_enabled=bool(reply.get("market_work_enabled",False)) and self.runtime_state=="ACTIVE"
                            if market_enabled and not self.meta:
                                try:
                                    self.meta={x["symbol"]:x for x in await linear_symbols(settings.bybit_rest_url)}
                                except Exception:
                                    log.exception("instrument metadata refresh failed",extra={"event":"metadata_refresh_failed"})
                            recovery=reply.get("recovery_profile") or {}
                            self.storage.set_replay_rate(recovery.get("minute_per_second",settings.replay_minute_per_second))
                            self.micro_storage.set_replay_rate(recovery.get("micro_per_second",settings.replay_micro_per_second))
                            assigned=set(reply.get("symbols",[])) if self.enabled and market_enabled else set()
                            requested_micro=set(reply.get("micro_symbols",[]))
                            recovering=bool(dbm.get("replay_active",False) or microm.get("replay_active",False))
                            async with self.assignment_lock:
                                response_age=time.monotonic()-response_received_at
                                if response_age >= max(1.0,3.0*settings.heartbeat_seconds):
                                    log.warning("discarding stale CONTROL heartbeat assignments",
                                                extra={"event":"stale_control_heartbeat","age_seconds":round(response_age,2)})
                                    continue
                                # Keep pressure shedding and assignment renewal atomic
                                # against the local watchdog and offline pressure loop.
                                self.pressure_drained=desired_drained_symbols(self.pressure,assigned)
                                new=assigned-self.pressure_drained
                                new_micro=(requested_micro & new) if not recovering else set()
                                self.last_assignment_heartbeat=time.monotonic()
                                assignments_changed=(new != self.wanted or new_micro != self.micro_wanted)
                                dead_trade_tasks=any(task.done() for task in self.trade_tasks.values())
                                dead_micro_tasks=any(task.done() for task in self.micro_tasks)
                                if assignments_changed or dead_trade_tasks or dead_micro_tasks:
                                    self.wanted=new
                                    self.micro_wanted=new_micro
                                    if dead_micro_tasks:
                                        # Force the microstructure collector group to be rebuilt.
                                        self.micro_signature=None
                                    await self.reconcile()
                            # Confirm this release only after an authenticated CONTROL
                            # heartbeat and successful assignment reconciliation.
                            ready_file=os.getenv('GRID_RELEASE_READY_FILE')
                            if ready_file:
                                pathlib.Path(ready_file).write_text(str(os.getpid()),encoding='ascii')
                        else:
                            log.warning("coordinator heartbeat rejected",extra={"event":"heartbeat_rejected"})
                except Exception:
                    log.exception("heartbeat failed",extra={"event":"heartbeat_failed"})
                    if internet_available():
                        mark_internet_success()
                    elif decommission_due(settings.decommission_days):
                        log.critical("offline decommission threshold reached",extra={"event":"self_decommission"})
                        await execute_command(
                            self,{"action":"uninstall","payload":{"purge_data":True}}
                        )
                        # Uninstaller unregisters the Scheduled Task. Return through
                        # normal Worker.run() cleanup instead of bypassing finally.
                        log.info("graceful self-decommission shutdown",
                                 extra={"event":"self_decommission_shutdown"})
                        return
                if self.restart_requested:
                    # Receipt is durable and ACK was attempted above. Return through
                    # Worker.run() so ML/process-tree and WAL cleanup runs first.
                    log.info("graceful worker restart requested",extra={"event":"worker_restart_requested"})
                    return
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

    async def _stop_raw_capture_tasks(self):
        tasks=list(self.trade_tasks.values())+list(self.micro_tasks)
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)
        self.trade_tasks.clear(); self.micro_tasks=[]

    async def reconcile(self):
        self._require_full_workload()
        raw_factory=getattr(self,'raw_capture_factory',None)
        if raw_factory is not None:
            # A terminal raw stop must not be turned into a fresh profile by
            # the legacy collector supervisor on its next assignment tick.
            tasks=list(self.trade_tasks.values())+list(self.micro_tasks)
            for task in tasks:
                if task.done():
                    try: task.result()
                    except RawCaptureError as error: self.raw_capture_failure=str(error)
                    except asyncio.CancelledError:
                        # Cancellation can interrupt an unknown sink outcome;
                        # it is not permission to construct a fresh budget.
                        self.raw_capture_failure='RAW_CAPTURE_CANCELLED_STOP'
                    except Exception:
                        self.raw_capture_failure='RAW_CAPTURE_TASK_OUTCOME_UNKNOWN'
            if getattr(self,'raw_capture_failure',None):
                await self._stop_raw_capture_tasks()
                return
        removed=[]
        for sym in list(self.trade_tasks):
            if sym not in self.wanted:
                task=self.trade_tasks.pop(sym);task.cancel();removed.append(task)
        if removed:
            outcomes=await asyncio.gather(*removed,return_exceptions=True)
            if raw_factory is not None and any(isinstance(result,BaseException) for result in outcomes):
                self.raw_capture_failure='RAW_CAPTURE_REMOVAL_OUTCOME_UNKNOWN'
                await self._stop_raw_capture_tasks()
                return
        for sym in self.wanted:
            existing=self.trade_tasks.get(sym)
            if existing is not None and existing.done():
                try:
                    existing.result()
                except asyncio.CancelledError:
                    log.warning('trade task cancelled; restarting',extra={'event':'trade_task_restart','symbol':sym})
                except Exception:
                    log.exception('trade task crashed; restarting',extra={'event':'trade_task_restart','symbol':sym})
                self.trade_tasks.pop(sym,None)
            if sym in self.meta and sym not in self.trade_tasks:
                self.trade_tasks[sym]=asyncio.create_task(self.trade_stream(sym))

        signature=tuple(sorted(self.micro_wanted))
        if signature != self.micro_signature:
            self.micro_signature=signature
            for t in self.micro_tasks:
                t.cancel()
            if self.micro_tasks:
                outcomes=await asyncio.gather(*self.micro_tasks,return_exceptions=True)
                if raw_factory is not None and any(isinstance(result,BaseException) for result in outcomes):
                    self.raw_capture_failure='RAW_CAPTURE_REASSIGNMENT_OUTCOME_UNKNOWN'
                    await self._stop_raw_capture_tasks()
                    return
            self.micro_tasks=[]
            collector=MicrostructureCollector(
                self.micro_storage,
                snapshot_ms=settings.microstructure_snapshot_ms,
                **({} if raw_factory is None else {'raw_capture_factory':raw_factory}),
            )
            symbols=list(signature)
            batch_size=8 if raw_factory is None else 1
            for i in range(0,len(symbols),batch_size):
                batch=symbols[i:i+batch_size]
                if batch:
                    self.micro_tasks.append(asyncio.create_task(collector.run_batch(batch)))
            log.info("microstructure assignment reconciled",extra={"event":"micro_assignment","component":f"{len(symbols)} symbols"})

    def _trade_handoff_state(self):
        for name in ('_pending_trade_rows','_pending_trade_locks','_pending_trade_reservations','_pending_trade_quality'):
            if not hasattr(self,name):setattr(self,name,{})

    async def _persist_trade_rows(self,symbol):
        self._trade_handoff_state()
        lock=self._pending_trade_locks.setdefault(symbol,asyncio.Lock())
        async with lock:
            rows=self._pending_trade_rows.get(symbol)
            while rows:
                retained=getattr(self.storage,'save_retained',None)
                receipt=await asyncio.wait_for((retained or self.storage.save)(rows[0]),timeout=PERSIST_TIMEOUT_SECONDS)
                if retained is not None:self.storage.acknowledge_admission(receipt)
                rows.popleft()
                self.pressure.observe_symbol(symbol,db_writes=1)

    async def _flush_trade_rows(self,timeout=5):
        self._trade_handoff_state()
        async def flush():
            for symbol in list(self._pending_trade_rows):await self._persist_trade_rows(symbol)
        try:await asyncio.wait_for(flush(),timeout=timeout)
        except (asyncio.TimeoutError,BufferError,RuntimeError,OSError):
            log.warning('pending finalized minutes remain unadmitted',extra={'event':'pending_minute_flush_incomplete'})

    async def trade_stream(self,symbol):
        self._require_full_workload()
        capture=self._raw_capture_for(symbol,settings.bybit_ws_url)
        tick=validated_tick(self.meta[symbol]["tick_size"])
        fp=FootprintBuilder(tick,settings.cluster_interval_seconds,finalization_delay_ms=2000)
        delays=backoff_delays()
        continuity=TradeContinuity(gap_ms=max(5000,settings.cluster_interval_seconds*1000//2))
        connected_once=False
        # Worker ownership survives pressure/assignment cancellation of this
        # collector. Only confirmed Storage receipts remove finalized rows.
        self._trade_handoff_state()
        pending_rows=self._pending_trade_rows.setdefault(symbol,deque())
        pending_quality=self._pending_trade_quality.setdefault(symbol,set())

        while True:
            disconnect_reason='transport_error'
            try:
                if capture is not None:
                    if not capture.matches(symbol,settings.bybit_ws_url):
                        raise RawCaptureError('RAW_CAPTURE_SOURCE_BINDING_CHANGED')
                    capture.begin_connection()
                await self._persist_trade_rows(symbol)
                await wait_for_internet()
                actual_endpoint=settings.bybit_ws_url
                async with websockets.connect(
                    actual_endpoint,
                    ping_interval=20,ping_timeout=20,max_queue=50000,close_timeout=5,
                    max_size=MAX_FRAME_BYTES
                ) as ws:
                    async def receive_frame():
                        raw=await ws.recv()
                        return await self._record_received_frame(raw,capture)
                    subscription_topic=f"publicTrade.{symbol}"
                    await ws.send(json.dumps({"op":"subscribe","args":[subscription_topic]}))
                    pending_frames=deque();pending_bytes=0
                    ack_deadline=asyncio.get_running_loop().time()+15
                    while True:
                        remaining=ack_deadline-asyncio.get_running_loop().time()
                        if remaining<=0:raise asyncio.TimeoutError("Bybit trade subscription ACK timeout")
                        raw,frame_ref=await asyncio.wait_for(receive_frame(),timeout=remaining)
                        ack,size=decode_frame(raw)
                        if ack.get("op")=="subscribe":
                            args=(ack.get("data") or {}).get("args") if isinstance(ack.get("data"),dict) else None
                            if args is None:args=ack.get("args")
                            if args is not None:
                                if not isinstance(args,list) or not all(isinstance(topic,str) for topic in args):
                                    raise RuntimeError("invalid Bybit trade subscription ACK args")
                                if subscription_topic not in args:continue
                            if ack.get("success") is not True:raise RuntimeError("Bybit trade subscription rejected")
                            if capture is not None: await capture.validated(frame_ref)
                            break
                        if ack.get("topic")==subscription_topic:
                            # Keep only fully validated, bounded trade batches.
                            # No aggregate or continuity state changes before ACK.
                            try:trades=parse_trades(ack,symbol,int(time.time()*1000))
                            except ValueError:
                                pending_quality.add("invalid_public_trade_frame")
                                log.warning("invalid public trade batch ignored",extra={"event":"invalid_public_trade_frame","symbol":symbol})
                                continue
                            if not trades:continue
                            if len(pending_frames)>=MAX_ACK_FRAMES or pending_bytes+size>MAX_ACK_BYTES:
                                raise RuntimeError("public trade subscription buffer limit")
                            pending_frames.append((trades,size,frame_ref));pending_bytes+=size
                    from .microstructure import public_market_connection
                    connection_context=public_market_connection(actual_endpoint)
                    tape=getattr(self,'micro_tape',None)
                    # An unmarked pre-existing RAM seed is not assigned a new
                    # connection identity. Existing arithmetic admission remains.
                    context_ready=tape is None or (symbol not in tape.state and symbol not in tape.cvd)
                    if connected_once and tape is not None:
                        preflight_tape([],tape,symbol)
                        # Discard only this symbol's admitted unclosed RAM state;
                        # never flush a partial bucket or touch persisted events.
                        tape.state.pop(symbol,None);tape.cvd.pop(symbol,None)
                        context_ready=True
                    if connected_once:
                        continuity.reconnect()
                        fp.mark_open_degraded(symbol,"ws_reconnect")
                        pending_quality.add("ws_reconnect")
                    connected_once=True
                    delays=backoff_delays()
                    while True:
                        if pending_frames:
                            trades,size,frame_ref=pending_frames.popleft();pending_bytes-=size
                        else:
                            raw,frame_ref=await asyncio.wait_for(receive_frame(),timeout=45)
                            try:
                                msg,_=decode_frame(raw)
                                if msg.get("topic")!=subscription_topic:continue
                                trades=parse_trades(msg,symbol,int(time.time()*1000))
                            except ValueError:
                                if capture is not None: await capture.gap('frame_invalid',frame_ref)
                                pending_quality.add("invalid_public_trade_frame")
                                log.warning("invalid public trade batch ignored",extra={"event":"invalid_public_trade_frame","symbol":symbol})
                                continue
                        if not trades:continue
                        # Cap both open buckets and the resulting pending rows;
                        # reject the whole batch before any aggregate mutation.
                        proposed=set(fp.buckets)|{(symbol,(trade.ts_ms//fp.interval_ms)*fp.interval_ms) for trade in trades}
                        if len(proposed)>MAX_OPEN_MINUTES:
                            pending_quality.add("public_trade_bucket_limit")
                            log.warning("public trade bucket limit",extra={"event":"public_trade_bucket_limit","symbol":symbol})
                            continue
                        try:
                            eligible=preflight_footprint(trades,fp)
                            if symbol in self.micro_wanted:preflight_tape(eligible,self.micro_tape,symbol)
                        except ValueError:
                            if capture is not None: await capture.gap('frame_invalid',frame_ref)
                            pending_quality.add('invalid_public_trade_frame')
                            log.warning('invalid public trade arithmetic',extra={'event':'invalid_public_trade_frame','symbol':symbol})
                            continue
                        if capture is not None:
                            await capture.validated(frame_ref,exchange_event_ms=max(t.ts_ms for t in trades))
                        finalize_at=int(time.time()*1000)
                        reserve=sum(start+fp.interval_ms+fp.finalization_delay_ms<=finalize_at for _,start in proposed)
                        occupied=sum(map(len,self._pending_trade_rows.values()))+sum(self._pending_trade_reservations.values())
                        if occupied+reserve>MAX_OPEN_MINUTES:
                            pending_quality.add('pending_minute_pressure')
                            raise BufferError('pending finalized minute limit')
                        self._pending_trade_reservations[symbol]=reserve
                        try:
                            for reason in pending_quality:fp.mark_open_degraded(symbol,reason)
                            self.pressure.observe_symbol(symbol,events=len(trades))
                            accepted=0
                            for trade in trades:
                                suspect_gap=continuity.observe(trade.ts_ms)
                                if not fp.add(trade):continue
                                accepted+=1
                                for reason in pending_quality:fp.mark_degraded(symbol,trade.ts_ms,reason)
                                if symbol in self.micro_wanted:
                                    tape_row=self.micro_tape.add(trade)
                                    if tape_row is not None:
                                        if connection_context is not None and context_ready:tape_row['_producer_connection']=dict(connection_context)
                                        await self.micro_storage.insert_event(symbol,tape_row["start_ms"],"trade_tape_250ms",tape_row)
                                if suspect_gap:fp.mark_degraded(symbol,trade.ts_ms,"trade_time_gap")
                            if accepted:pending_quality.clear()
                            if pending_frames:continue
                            for row in fp.pop_closed(finalize_at):
                                from .provenance import producer
                                if not hasattr(self,"provenance_source"):
                                    from .resources import NODE_ID
                                    self.provenance_source=producer(NODE_ID,os.environ.get("GRID_SOURCE_REVISION",""),settings.bybit_ws_url)
                                row["source_provenance"]=self.provenance_source
                                pending_rows.append(row)
                        finally:self._pending_trade_reservations.pop(symbol,None)
                        await self._persist_trade_rows(symbol)
            except RawCaptureError:
                raise
            except asyncio.CancelledError:
                disconnect_reason='cancelled'
                self._pending_trade_reservations.pop(symbol,None)
                if not pending_rows:
                    self._pending_trade_rows.pop(symbol,None)
                    self._pending_trade_locks.pop(symbol,None)
                if not pending_quality:self._pending_trade_quality.pop(symbol,None)
                raise
            except BufferError:
                if capture is not None:
                    await capture.gap('buffer_pressure')
                    raise RawCaptureError('RAW_CAPTURE_PRESSURE_STOP') from None
                pending_quality.add("wal_pressure")
                self.pressure.state="CRITICAL"
                self.pressure.bad_ticks=max(self.pressure.bad_ticks,10)
                log.error("local WAL pressure; draining live symbols until database catches up",
                          extra={"event":"wal_pressure","symbol":symbol})
                await asyncio.sleep(min(5,max(.1,settings.heartbeat_seconds)))
            except Exception:
                if capture is not None:
                    raise RawCaptureError('RAW_CAPTURE_TRANSPORT_STOP') from None
                pending_quality.add("stream_failure")
                d=next(delays)
                log.exception("trade stream failed",extra={"event":"reconnect","symbol":symbol,"delay":d})
                await asyncio.sleep(d)
            finally:
                if capture is not None:
                    try: await capture.disconnect(disconnect_reason)
                    except RawCaptureError:
                        if disconnect_reason!='cancelled': raise
                        log.warning('raw disconnect observation unavailable during cancellation',extra={'event':'raw_capture_cancel_unknown'})

    async def run(self):
        self._require_full_workload()
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
        assignment_watchdog_task=asyncio.create_task(self.assignment_watchdog())
        if ml_runtime_ready():
            client=MLTransportClient(NODE_ID)
            def ml_can_claim():
                try:
                    snap=snapshot()
                    return (self.enabled and not self.operator_stopped and not self.bootstrap_paused
                            and self.runtime_state=="ACTIVE"
                            and snap.get("disk_pressure_state")=="NORMAL")
                except Exception:
                    return False
            self.ml_task=asyncio.create_task(
                ml_agent_loop(client,self.ml_stop,poll_seconds=5,can_claim=ml_can_claim))
        self._start_data_first_consumer()
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
            assignment_watchdog_task.cancel()
            await asyncio.gather(health_task,assignment_watchdog_task,return_exceptions=True)
            self.ml_stop.set()
            if self.ml_task is not None:
                self.ml_task.cancel()
                await asyncio.gather(self.ml_task,return_exceptions=True)
            if self.data_first_task is not None:
                self.data_first_task.cancel()
                await asyncio.gather(self.data_first_task,return_exceptions=True)
            await self._flush_trade_rows()
            await self.micro_storage.close()
            await self.storage.close()

async def main():
    await Worker().run()

if __name__=="__main__":
    asyncio.run(main())
