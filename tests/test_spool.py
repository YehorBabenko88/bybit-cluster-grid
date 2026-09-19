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
