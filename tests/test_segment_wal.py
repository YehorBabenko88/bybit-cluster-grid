import asyncio,json
import pytest
from grid.segment_wal import SegmentWAL

def test_wal_append_recover_checkpoint(tmp_path):
    async def run():
        w=SegmentWAL(tmp_path,max_bytes=10000,segment_bytes=200)
        a=await w.append({"symbol":"BTC","n":1})
        b=await w.append({"symbol":"ETH","n":2})
        assert [x[0] for x in w.recover()]==[a,b]
        await w.ack(a)
        assert [x[0] for x in w.recover()]==[b]
        w2=SegmentWAL(tmp_path,max_bytes=10000,segment_bytes=200)
        assert [x[0] for x in w2.recover()]==[b]
    asyncio.run(run())

def test_wal_crc_rejects_corrupt_record(tmp_path):
    async def run():
        w=SegmentWAL(tmp_path,max_bytes=10000)
        await w.append({"ok":1})
        seg=w._segments()[0]
        obj=json.loads(seg.read_text().splitlines()[0])
        obj["payload"]={"ok":999}
        seg.write_text(json.dumps(obj)+"\n",encoding="utf-8")
        with pytest.raises(RuntimeError,match="corrupt WAL record"):
            w.recover()
    asyncio.run(run())

def test_wal_rotates_segments(tmp_path):
    async def run():
        w=SegmentWAL(tmp_path,max_bytes=100000,segment_bytes=80)
        for i in range(6): await w.append({"i":i,"payload":"x"*30})
        assert len(w._segments())>1
        assert len(w.recover())==6
    asyncio.run(run())

def test_wal_hard_capacity(tmp_path):
    async def run():
        w=SegmentWAL(tmp_path,max_bytes=100)
        failed=False
        for i in range(20):
            try: await w.append({"x":"z"*30,"i":i})
            except BufferError:
                failed=True; break
        assert failed
        assert w.ratio()<=1.0
    asyncio.run(run())
