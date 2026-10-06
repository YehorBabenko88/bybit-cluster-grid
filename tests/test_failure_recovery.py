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
    assert 'asyncio.wait_for(ws.recv(),timeout=15)' in worker
    assert 'asyncio.wait_for(ws.recv(),timeout=45)' in worker
    assert 'ack.get("success") is not True' in micro
    assert 'asyncio.wait_for(ws.recv(),timeout=15)' in micro
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


def test_pending_release_watchdog_rolls_back_only_fast_crash_loop():
    from pathlib import Path
    h=Path("installer/release-health.ps1").read_text(encoding="utf-8")
    assert "$RuntimeSeconds -ge 60" in h
    assert "$count -lt 3" in h
    assert '"previous.version"' in h
    assert '"current.version"' in h
    assert "exit 75" in h
    install=Path("installer/install.ps1").read_text(encoding="utf-8")
    assert 'release-health.ps1' in install
    for name in ("installer/launcher.ps1","installer/archive-launcher.ps1",
                 "installer/coordinator-launcher.ps1"):
        s=Path(name).read_text(encoding="utf-8")
        assert "release-health.ps1" in s
        assert "-Phase AfterExit" in s
        assert "$runtime=" in s
        assert "if($LASTEXITCODE -eq 75){exit 75}" in s


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
    manifest=i.index('"postgres-owned.json"')
    assert marker < process < manifest
    assert "Remove-Item $Installing" in i


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
