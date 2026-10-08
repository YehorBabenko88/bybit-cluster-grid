import asyncio
from grid.segment_wal import SegmentWAL
from grid.write_queue import BoundedWriteQueue

def test_db_outage_retries_then_drains_wal(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        attempts={"n":0}; committed=[]
        async def db_writer(record_id,row):
            attempts["n"]+=1
            if attempts["n"]<=2:
                raise ConnectionError("postgres unavailable")
            committed.append(row["n"])
            await wal.ack(record_id)
        q=BoundedWriteQueue(db_writer,maxsize=10,workers=1,retry_base_seconds=.01,retry_max_seconds=.02)
        await q.start()
        for n in range(3):
            rid=await wal.append({"n":n})
            await q.put(rid,{"n":n})
        await asyncio.wait_for(q.q.join(),8)
        assert committed==[0,1,2]
        assert wal.recover()==[]
        assert q.metrics()["write_failures"]==2
        for t in q.tasks: t.cancel()
    asyncio.run(run())

def test_restart_replays_only_uncheckpointed_records(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        ids=[]
        for n in range(4):
            ids.append(await wal.append({"n":n}))
        await wal.ack(ids[1])
        # Simulate process death: construct a new WAL object from the same directory.
        recovered=SegmentWAL(tmp_path,max_bytes=100000).recover()
        assert [row["n"] for _,row in recovered]==[2,3]
    asyncio.run(run())

def test_upsert_style_retry_does_not_lose_checkpoint_order(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        committed={}
        for n in range(3):
            rid=await wal.append({"symbol":"BTC","minute":n})
            # Simulates idempotent PostgreSQL ON CONFLICT upsert.
            row={"symbol":"BTC","minute":n}
            committed[(row["symbol"],row["minute"])]=row
            committed[(row["symbol"],row["minute"])]=row
            await wal.ack(rid)
        assert len(committed)==3
        assert wal.recover()==[]
    asyncio.run(run())


def test_corrupt_primary_checkpoint_recovers_from_backup(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        ids=[await wal.append({"n":n}) for n in range(4)]
        await wal.ack(ids[0])
        await wal.ack(ids[1])
        # Simulate a torn primary checkpoint write after a sudden power loss.
        wal.checkpoint.write_text("CORRUPT",encoding="ascii")
        restarted=SegmentWAL(tmp_path,max_bytes=100000)
        recovered=restarted.recover()
        assert [row["n"] for _,row in recovered]==[1,2,3]
        # Replaying one extra idempotent record is safe; replaying from zero is not.
        assert restarted._checkpoint_id()==ids[0]
    asyncio.run(run())


def test_wal_rejects_write_before_exceeding_capacity(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=180)
        await wal.append({"payload":"x"*40})
        before=wal.bytes_used()
        try:
            await wal.append({"payload":"y"*200})
            assert False,"capacity guard did not fire"
        except BufferError:
            pass
        assert wal.bytes_used()==before
    asyncio.run(run())


def test_checkpoint_staging_paths_are_distinct(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        first=await wal.append({"n":1})
        second=await wal.append({"n":2})
        await wal.ack(first)
        await wal.ack(second)
        assert wal._checkpoint_id()==second
        assert wal.checkpoint.read_text(encoding="ascii").strip()==str(second)
        assert wal.checkpoint_backup.read_text(encoding="ascii").strip()==str(first)
        assert not (tmp_path/"checkpoint.next").exists()
        assert not (tmp_path/"checkpoint.backup.next").exists()
    asyncio.run(run())


def test_queue_shutdown_is_bounded_when_sink_is_down():
    async def run():
        blocker=asyncio.Event()
        async def writer(*_):
            await blocker.wait()
        q=BoundedWriteQueue(writer,maxsize=4,workers=1)
        await q.start()
        await q.put(1,{"n":1})
        await q.close(drain_timeout=.02)
        assert q.tasks==[]
    asyncio.run(run())


def test_websocket_collectors_require_subscription_ack_and_stall_timeout():
    worker=__import__("pathlib").Path("grid/worker.py").read_text(encoding="utf-8")
    micro=__import__("pathlib").Path("grid/microstructure.py").read_text(encoding="utf-8")
    assert 'ack.get("success") is not True' in worker
    assert 'ack_deadline=asyncio.get_running_loop().time()+15' in worker
    assert 'asyncio.wait_for(ws.recv(),timeout=remaining)' in worker
    assert 'asyncio.wait_for(ws.recv(),timeout=45)' in worker
    assert 'ack.get("success") is not True' in micro
    assert 'ack_deadline=asyncio.get_running_loop().time()+15' in micro
    assert 'asyncio.wait_for(ws.recv(),timeout=remaining)' in micro
    assert 'asyncio.wait_for(ws.recv(),timeout=45)' in micro


def test_power_loss_partial_wal_tail_is_truncated_before_next_append(tmp_path):
    async def run():
        from grid.segment_wal import SegmentWAL
        root=tmp_path/"wal"
        w=SegmentWAL(root,max_bytes=1024*1024,segment_bytes=1024*1024)
        first=await w.append({"n":1})
        seg=w._segments()[-1]
        with open(seg,"ab") as f:
            f.write(b'{"id":999,"crc32":12,"payload":')
            f.flush()
        restarted=SegmentWAL(root,max_bytes=1024*1024,segment_bytes=1024*1024)
        second=await restarted.append({"n":2})
        recovered=restarted.recover()
        assert [rid for rid,_ in recovered]==[first,second]
        assert [payload["n"] for _,payload in recovered]==[1,2]
    asyncio.run(run())


def test_wal_startup_removes_crash_staging_files(tmp_path):
    from grid.segment_wal import SegmentWAL
    root=tmp_path/"wal";root.mkdir()
    (root/"checkpoint.next").write_text("12",encoding="ascii")
    (root/"checkpoint.backup.next").write_text("11",encoding="ascii")
    SegmentWAL(root)
    assert not (root/"checkpoint.next").exists()
    assert not (root/"checkpoint.backup.next").exists()


def test_release_install_recovers_power_loss_replaced_window(tmp_path):
    import zipfile
    from grid.update_manager import install_release
    root=tmp_path/"install"; releases=root/"releases"; releases.mkdir(parents=True)
    old=releases/"v1"; old.mkdir(); (old/"run_worker.py").write_text("old",encoding="utf-8")
    replaced=releases/"v1.replaced"
    old.rename(replaced)  # power loss after target -> backup, before staging -> target
    package=tmp_path/"v1.zip"
    with zipfile.ZipFile(package,"w") as z:z.writestr("run_worker.py","new")
    target=install_release(package,"v1",root)
    assert (target/"run_worker.py").read_text(encoding="utf-8")=="new"
    assert not replaced.exists()


def test_launchers_fallback_current_previous_bootstrap():
    from pathlib import Path
    for name,entry in (
        ("installer/launcher.ps1","run_worker.py"),
        ("installer/coordinator-launcher.ps1","grid\\coordinator.py"),
        ("installer/archive-launcher.ps1","grid\\archive_service.py"),
    ):
        s=Path(name).read_text(encoding="utf-8")
        assert '@("current.version","previous.version")' in s
        assert entry in s
        assert '($cv+".replaced")' in s
        assert 'Join-Path $InstallRoot "bootstrap"' in s


def test_release_markers_are_fsynced_before_atomic_replace():
    from pathlib import Path
    s=Path("grid/update_manager.py").read_text(encoding="utf-8")
    block=s.split("def _write_marker",1)[1].split("def current_version",1)[0]
    assert "f.flush(); os.fsync(f.fileno())" in block
    assert "os.replace(tmp,marker)" in block


def test_update_marks_release_pending_for_boot_health():
    from pathlib import Path
    u=Path("grid/update_manager.py").read_text(encoding="utf-8")
    a=Path("grid/agent_commands.py").read_text(encoding="utf-8")
    assert 'def mark_pending(' in u
    assert '"pending.version"' in u
    assert "mark_pending(install_root,version)" in a


def test_release_supervisor_rolls_back_after_three_fast_crashes(tmp_path):
    from grid.release_supervisor import _after_exit
    root=tmp_path/"install"; releases=root/"releases"; releases.mkdir(parents=True)
    (releases/"bad").mkdir(); (releases/"bad"/"run_worker.py").write_text("",encoding="utf-8")
    (releases/"good").mkdir(); (releases/"good"/"run_worker.py").write_text("",encoding="utf-8")
    (root/"current.version").write_text("bad",encoding="utf-8")
    (root/"previous.version").write_text("good",encoding="utf-8")
    (root/"pending.version").write_text("bad",encoding="utf-8")
    assert _after_exit(root,"bad",2) is False
    assert _after_exit(root,"bad",3) is False
    assert _after_exit(root,"bad",4) is True
    assert (root/"current.version").read_text(encoding="utf-8")=="good"
    assert not (root/"pending.version").exists()


def test_release_supervisor_confirms_same_live_process(tmp_path):
    import subprocess,sys,threading
    from grid.release_supervisor import _confirm
    root=tmp_path/"install";root.mkdir()
    (root/"pending.version").write_text("v2",encoding="utf-8")
    p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(.5)"])
    _confirm(root,"v2",p,.05)
    assert not (root/"pending.version").exists()
    p.wait()


def test_archive_cannot_trigger_release_rollback():
    from pathlib import Path
    a=Path("installer/archive-launcher.ps1").read_text(encoding="utf-8")
    assert "never decides" in a
    assert "release-health.ps1" not in a
    assert "grid.archive_service" in a


def test_main_launchers_use_release_supervisor():
    from pathlib import Path
    for name in ("installer/launcher.ps1","installer/coordinator-launcher.ps1"):
        s=Path(name).read_text(encoding="utf-8")
        assert "grid.release_supervisor" in s
        assert "--install-root $InstallRoot" in s
        assert "release-health.ps1" not in s

def test_bootstrap_repairs_partial_owned_python_transactionally():
    from pathlib import Path
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert '$OwnedStage=$OwnedRoot+".staging"' in b
    assert '$OwnedPrevious=$OwnedRoot+".previous"' in b
    assert "Bundled Grid Python runtime failed staging validation" in b
    assert "Move-Item $OwnedStage $OwnedRoot" in b
    assert "Move-Item $OwnedPrevious $OwnedRoot" in b


def test_postgres_install_is_journaled_before_installer_mutation():
    from pathlib import Path
    i=Path("installer/install-postgres.ps1").read_text(encoding="utf-8")
    marker=i.index('"postgres-installing.json"')
    process=i.index("Start-Process -FilePath $Installer")
    assert '"postgres-owned.json"' not in i
    assert marker < process
    assert "postgres-installing.json remains the sole recovery journal" in i


def test_postgres_partial_repair_requires_transaction_marker():
    from pathlib import Path
    p=Path("installer/provision_postgres.ps1").read_text(encoding="utf-8")
    assert 'if(Test-Path $Installing)' in p
    assert 'sc.exe delete "BybitClusterGridPostgres"' in p
    assert "without committed credentials or transaction marker" in p
    assert "Unrelated PostgreSQL exists" in p


def test_windows_ci_parses_every_installer_script():
    from pathlib import Path
    w=Path(".github/workflows/windows-bundle.yml").read_text(encoding="utf-8")
    assert "Parse all PowerShell installer scripts" in w
    assert "Language.Parser]::ParseFile" in w
    assert "PowerShell parse failed" in w


def test_install_does_not_register_agent_before_role_decision():
    from pathlib import Path
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    reg='Register-ScheduledTask -TaskName $TaskName'
    assert s.count(reg)==1
    normal=s.split('}else{',1)[-1]
    assert reg in normal


def test_tailscale_zero_touch_bootstrap_uses_silent_msi():
    from pathlib import Path
    t=Path("installer/configure-tailscale.ps1").read_text(encoding="utf-8")
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert "TS_NOLAUNCH=1" in t
    assert "TS_UNATTENDEDMODE=always" in t
    assert "TS_ONBOARDING_FLOW=hide" in t
    assert "set --unattended=true" in t
    assert "TailscaleMsiPath" in b


def test_tailscale_provisioning_is_control_side_one_time_tagged():
    from pathlib import Path
    p=Path("grid/tailscale_provisioning.py").read_text(encoding="utf-8")
    assert "/api/v2/oauth/token" in p
    assert "/api/v2/tailnet/-/keys" in p
    assert '"reusable":False' in p
    assert '"ephemeral":False' in p
    assert '"preauthorized":True' in p
    assert '"tags":tag_list' in p


def test_bootstrap_envelope_is_admin_only_and_does_not_return_oauth_secret():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    block=c.split('@app.post("/bootstrap/envelope")',1)[1].split('@app.post("/enroll")',1)[0]
    assert "auth(x_grid_token)" in block
    assert "create_one_time_auth_key" in block
    assert '"tailscale_auth_key":tailscale_key' in block
    assert "tailscale_oauth_client_secret" in block
    assert '"tailscale_oauth_client_secret"' not in block


def test_bootstrap_envelope_is_destroyed_after_use():
    from pathlib import Path
    s=Path("installer/bootstrap-from-envelope.ps1").read_text(encoding="utf-8")
    assert "Bootstrap envelope expired" in s
    assert "-AgentMode AUTO" in s
    assert "finally" in s
    assert "Remove-Item $full" in s


def test_bootstrap_envelope_requires_non_loopback_control_address():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    block=c.split('@app.post("/bootstrap/envelope")',1)[1].split('@app.post("/enroll")',1)[0]
    assert "reachable non-loopback coordinator_url is required" in block
    assert '"coordinator_url":coordinator_url' in block


def test_migrations_are_serialized_between_control_services():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert "pg_advisory_lock" in m
    assert "pg_advisory_unlock" in m
    assert "finally:" in m


def test_postgres_transaction_closes_only_after_dsn_commit():
    from pathlib import Path
    i=Path("installer/install-postgres.ps1").read_text(encoding="utf-8")
    p=Path("installer/provision_postgres.ps1").read_text(encoding="utf-8")
    assert "postgres-installing.json remains the sole recovery journal" in i
    assert p.index('Add-EnvOnce "POSTGRES_DSN"') < p.rindex("Remove-Item $Installing")
    assert "configure-postgres.ps1" in p


def test_owned_postgres_config_is_idempotently_managed():
    from pathlib import Path
    p=Path("installer/configure-postgres.ps1").read_text(encoding="utf-8")
    assert "# BEGIN BybitClusterGrid managed" in p
    assert "max_wal_size = '2GB'" in p
    assert "log_truncate_on_rotation = off" in p
    assert "postgresql-%Y-%m-%d_%H%M.log" in p
    assert "invalid ownership manifest" in p


def test_control_env_acl_protects_database_and_telegram_secrets():
    from pathlib import Path
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert '*S-1-5-18:(F)' in b
    assert '*S-1-5-32-544:(F)' in b
    assert '"Administrators:F"' not in b


def test_telegram_validates_api_and_credentials_before_polling():
    from pathlib import Path
    t=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'await _tg_api(session,"getMe",retries=1)' in t
    assert "telegram_auth_failed" in t
    assert "r.status==429" in t
    assert 'data.get("ok") is not True' in t


def test_one_click_worker_package_contains_full_installer_and_no_github_login():
    from pathlib import Path
    p=Path("installer/new-worker-package.ps1").read_text(encoding="utf-8")
    assert 'Copy-Item (Join-Path $PSScriptRoot "*") $installerOut -Recurse -Force' in p
    assert "Install-Grid.cmd" in p
    assert "tailscale.msi" in p
    assert "bootstrap-envelope.json" in p
    assert "gh auth" not in p.lower()


def test_worker_install_requires_control_heartbeat_acceptance():
    from pathlib import Path
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    v=Path("installer/verify-worker-acceptance.ps1").read_text(encoding="utf-8")
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert "verify-worker-acceptance.ps1" in b
    assert b.index("verify-worker-acceptance.ps1") < b.index('status="installed"')
    assert "/nodes/{node_id}/acceptance" in c
    assert "authenticate_agent" in c
    assert '"X-Node-Credential"=$credential' in v
    assert "healthy heartbeat" in v


def test_windows_grid_tasks_ignore_battery_power_for_recovery():
    from pathlib import Path
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    assert "$Settings.DisallowStartIfOnBatteries=$false" in s
    assert "$Settings.StopIfGoingOnBatteries=$false" in s
    assert "-RestartCount 999" in s
    assert "-StartWhenAvailable" in s


def test_update_manager_recognizes_real_control_entrypoint(tmp_path):
    from grid.update_manager import _release_runnable
    release=tmp_path/"control"; (release/"grid").mkdir(parents=True)
    (release/"grid"/"coordinator.py").write_text("",encoding="utf-8")
    assert _release_runnable(release)


def test_manual_rollback_clears_pending_health_state(tmp_path):
    from grid.update_manager import rollback
    root=tmp_path/"install"; releases=root/"releases"; releases.mkdir(parents=True)
    for v in ("bad","good"):
        d=releases/v; d.mkdir(); (d/"run_worker.py").write_text("",encoding="utf-8")
    (root/"current.version").write_text("bad",encoding="utf-8")
    (root/"previous.version").write_text("good",encoding="utf-8")
    (root/"pending.version").write_text("bad",encoding="utf-8")
    (root/"pending-crashes.txt").write_text("2",encoding="utf-8")
    assert rollback(root)=="good"
    assert not (root/"pending.version").exists()
    assert not (root/"pending-crashes.txt").exists()


def test_control_self_update_rejects_non_https_before_mutation():
    import asyncio
    from grid.control_self_update import apply
    try:
        asyncio.run(apply("v","http://example.invalid/x.zip","0"*64))
    except ValueError as e:
        assert "HTTPS" in str(e)
    else:
        raise AssertionError("non-HTTPS CONTROL update accepted")


def test_control_update_status_journal_is_atomic(tmp_path):
    import json
    from grid.control_self_update import _status
    _status(tmp_path,state="preflight",version="v2")
    p=tmp_path/"control-update-status.json"
    data=json.loads(p.read_text(encoding="utf-8"))
    assert data["state"]=="preflight" and data["version"]=="v2"
    assert not (tmp_path/"control-update-status.json.tmp").exists()


def test_control_update_unlock_removes_only_own_lock(tmp_path):
    import os
    from grid.control_self_update import _unlock_own
    p=tmp_path/"control-update.lock"
    p.write_text(str(os.getpid()),encoding="ascii")
    _unlock_own(tmp_path)
    assert not p.exists()
    p.write_text("99999999",encoding="ascii")
    _unlock_own(tmp_path)
    assert p.exists()


def test_control_update_api_requires_completed_registered_rollout():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert '@app.post("/control/update")' in c
    assert 'rollout_status"]!="complete"' in c
    assert "registered release metadata is invalid" in c
    assert 'payload.get("package_url")' not in c
    assert '@app.get("/control/update/status")' in c


def test_telegram_control_update_uses_promoted_registered_release_only():
    from pathlib import Path
    t=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'cmd=="/controlupdate"' in t
    assert "r.channel='stable'" in t
    assert "r.enabled=true" in t
    assert 'rel["rollout_status"]!="complete"' in t
    assert 'cmd=="/controlupdatestatus"' in t


def test_pending_journal_precedes_current_switch_for_all_updaters():
    from pathlib import Path
    for name in ("grid/agent_commands.py","grid/control_self_update.py"):
        text=Path(name).read_text(encoding="utf-8")
        section=text[text.index("previous=current_version"):]
        assert section.index("mark_pending") < section.index("switch_current")
        assert "clear_pending(install_root)" in section


def test_control_update_overlap_gate_covers_pending_health_window():
    from pathlib import Path
    for name in ("grid/coordinator.py","grid/telegram_bot.py"):
        text=Path(name).read_text(encoding="utf-8")
        assert "pending.version" in text
        assert "control-update.lock" in text
        assert "health verification already running" in text


def test_wal_replay_waits_for_sink_ack_before_live_producers():
    from pathlib import Path
    for name in ("grid/storage.py","grid/micro_event_storage.py"):
        text=Path(name).read_text(encoding="utf-8")
        replay=text[text.index("async def _replay"):text.index("async def ",text.index("async def _replay")+10)]
        assert "await self.write_queue.q.join()" in replay
        assert "else:\n            self.replay_done.set()" in replay
        assert "finally:\n            self.replay_done.set()" not in replay


def test_archive_does_not_mutate_consumed_feature_source():
    from pathlib import Path
    text=Path("grid/archive_materializer.py").read_text(encoding="utf-8")
    assert "SELECT EXISTS(SELECT 1 FROM market_features_1m" in text
    assert "DELETE FROM footprint_1m" in text
    assert "EXCLUDED.trade_count >= candles_1m.trade_count" in text


def test_dataset_cutoff_includes_label_horizon():
    from pathlib import Path
    text=Path("grid/ml_dataset_builder.py").read_text(encoding="utf-8")
    assert "COALESCE(label_end_ts,event_ts)<=$1" in text


def test_control_firewall_is_tailnet_only():
    from pathlib import Path
    text=Path("installer/configure-control-firewall.ps1").read_text(encoding="utf-8")
    assert "100.64.0.0/10" in text
    assert "fd7a:115c:a1e0::/48" in text
    assert "LocalSubnet" not in text


def test_release_update_verifies_internal_manifest_before_switch():
    from pathlib import Path
    text=Path("grid/agent_commands.py").read_text(encoding="utf-8")
    update=text[text.index("async def _update"):text.index("def _grid_log_tail")]
    assert 'manifest=target/"release-manifest.json"' in update
    assert 'report=verify_manifest(target,manifest)' in update
    assert 'report.get("version")' in update
    assert update.index("verify_manifest(target,manifest)") < update.index("switch_current(install_root,version)")


def test_postgres_ownership_is_committed_after_dsn():
    from pathlib import Path
    install=Path("installer/install-postgres.ps1").read_text(encoding="utf-8")
    provision=Path("installer/provision_postgres.ps1").read_text(encoding="utf-8")
    assert "postgres-owned.json" not in install
    dsn=provision.index('Add-EnvOnce "POSTGRES_DSN"')
    manifest=provision.index("$finalManifest=[ordered]@{",dsn)
    journal=provision.index("Remove-Item $Installing",manifest)
    assert dsn < manifest < journal


def test_windows_secret_acls_do_not_depend_on_localized_group_names():
    from pathlib import Path
    for name in ("installer/enroll.ps1","installer/new-bootstrap-envelope.ps1"):
        text=Path(name).read_text(encoding="utf-8")
        assert "*S-1-5-32-544" in text
        assert "Administrators:" not in text


def test_strategy_retry_clears_partial_prior_attempt_results():
    from pathlib import Path
    text=Path("grid/strategy_jobs.py").read_text(encoding="utf-8")
    claim=text[text.index("async def claim_job"):text.index("async def requeue_job")]
    assert 'DELETE FROM strategy_results WHERE job_id=$1' in claim
