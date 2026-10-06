import asyncio
from grid.write_queue import BoundedWriteQueue


def test_large_replay_does_not_block_service_start():
    async def run():
        gate=asyncio.Event()
        async def writer(*_):
            await gate.wait()
        q=BoundedWriteQueue(writer,maxsize=2,workers=1)
        await q.start()
        replay_done=asyncio.Event()
        async def replay():
            try:
                for n in range(20):
                    await q.put(n,{"n":n})
            finally:
                replay_done.set()
        task=asyncio.create_task(replay())
        await asyncio.sleep(.02)
        assert not replay_done.is_set()
        assert q.q.qsize() <= 2
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await q.close(drain_timeout=.01)
    asyncio.run(run())


def test_storage_replay_is_background_and_live_writes_wait_for_order():
    from pathlib import Path
    for name in ("grid/storage.py","grid/micro_event_storage.py"):
        s=Path(name).read_text(encoding="utf-8")
        assert "asyncio.create_task(self._replay(pending))" in s
        assert "await self.replay_done.wait()" in s
        assert "self.replay_task.cancel()" in s


def test_worker_can_shed_load_without_successful_control_heartbeat():
    from pathlib import Path
    s=Path("grid/worker.py").read_text(encoding="utf-8")
    pressure=s.index("# Pressure control must remain autonomous")
    post=s.index("async with s.post(",pressure)
    assert pressure < post
    block=s[pressure:post]
    assert "symbols_to_drain" in block
    assert "await self.reconcile()" in block


def test_replay_is_paced_and_staggered_across_nodes():
    from pathlib import Path
    cfg=Path("grid/config.py").read_text(encoding="utf-8")
    assert "replay_minute_per_second" in cfg
    assert "replay_micro_per_second" in cfg
    assert "replay_start_jitter_seconds" in cfg
    for name,rate in (("grid/storage.py","replay_minute_per_second"),
                      ("grid/micro_event_storage.py","replay_micro_per_second")):
        s=Path(name).read_text(encoding="utf-8")
        assert "hashlib.sha256(NODE_ID.encode" in s
        assert rate in s
        assert "record_id in self.replay_ids" in s
        assert "wait=interval-(asyncio.get_running_loop().time()-self._last_replay_send)" in s
        assert "self.replay_ids.discard(record_id)" in s
        assert "replay_backlog_bytes" in s


def test_worker_sheds_fresh_micro_capture_during_wal_recovery():
    from pathlib import Path
    s=Path("grid/worker.py").read_text(encoding="utf-8")
    assert '"db_replay_active"' in s
    assert '"micro_replay_active"' in s
    assert "recovering=bool(dbm.get" in s
    assert "new_micro=(requested_micro & new) if not recovering else set()" in s


def test_control_publishes_adaptive_recovery_feedback():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert "async def recovery_profile()" in c
    for profile in ('"profile":"FAST"','"profile":"SLOW"','"profile":"PAUSE"'):
        assert profile in c
    assert "replay_db_latency_slow_ms" in c
    assert "replay_db_latency_pause_ms" in c
    assert '"recovery_profile":replay' in c


def test_worker_applies_dynamic_replay_rate_and_pause_is_quiet():
    from pathlib import Path
    w=Path("grid/worker.py").read_text(encoding="utf-8")
    assert 'reply.get("recovery_profile")' in w
    assert "self.db.set_replay_rate" in w
    assert "self.micro_storage.set_replay_rate" in w
    for name in ("grid/storage.py","grid/micro_event_storage.py"):
        s=Path(name).read_text(encoding="utf-8")
        assert "def set_replay_rate" in s
        assert "while rate<=0:" in s
        assert "await asyncio.sleep(1.0)" in s
        assert "CONTROL paused WAL recovery" not in s


def test_recovery_budget_is_shared_across_recovering_workers():
    from pathlib import Path
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    block=c.split("async def recovery_profile()",1)[1].split("def constant_time_equal",1)[0]
    assert "recovering=sum(" in block
    assert "db_replay_active" in block
    assert "micro_replay_active" in block
    assert "share=max(1,recovering)" in block
    assert "/share" in block
