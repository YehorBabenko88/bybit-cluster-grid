import asyncio,json
from grid.spool import DiskSpool

def test_spool_append_recover_ack(tmp_path):
    async def run():
        s=DiskSpool(tmp_path,max_bytes=10000)
        path=await s.append({"symbol":"BTCUSDT","x":1})
        assert s.bytes_used()>0
        recovered=s.recover()
        assert len(recovered)==1
        assert recovered[0][1]["symbol"]=="BTCUSDT"
        await s.ack(path)
        assert s.recover()==[]
    asyncio.run(run())

def test_spool_capacity_is_hard_bounded(tmp_path):
    async def run():
        s=DiskSpool(tmp_path,max_bytes=30)
        await s.append({"x":"1234567890"})
        try:
            await s.append({"x":"1234567890"})
        except BufferError:
            pass
        else:
            raise AssertionError("spool must reject writes beyond hard capacity")
        assert s.ratio()<=1.0
    asyncio.run(run())

def test_corrupt_entry_does_not_break_recovery(tmp_path):
    async def run():
        s=DiskSpool(tmp_path,max_bytes=10000)
        await s.append({"ok":1})
        (s.pending/"000-bad.json").write_text("{bad",encoding="utf-8")
        rows=s.recover()
        assert any(row.get("ok")==1 for _,row in rows)
    asyncio.run(run())


def test_corrupt_entry_is_quarantined_and_counts_toward_capacity(tmp_path):
    async def run():
        s=DiskSpool(tmp_path,max_bytes=40)
        bad=s.pending/"000-bad.json"
        bad.write_text("{broken",encoding="utf-8")
        assert s.recover()==[]
        assert not bad.exists()
        assert (s.quarantine/bad.name).exists()
        assert s.bytes_used()==len("{broken")
        assert s.recover()==[]
    asyncio.run(run())


def test_ack_cannot_delete_files_outside_pending_spool(tmp_path):
    async def run():
        s=DiskSpool(tmp_path)
        other=tmp_path/"important.json"
        other.write_text("keep",encoding="utf-8")
        try:
            await s.ack(other)
        except ValueError:
            pass
        else:
            raise AssertionError("external path must be rejected")
        assert other.read_text(encoding="utf-8")=="keep"
    asyncio.run(run())
