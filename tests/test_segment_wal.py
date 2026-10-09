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
        with pytest.raises(ValueError,match="Corrupt WAL record"):
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


def test_restart_repairs_valid_tail_without_newline_before_append(tmp_path):
    async def run():
        first=SegmentWAL(tmp_path,max_bytes=10000)
        rid1=await first.append({"symbol":"BTC","n":1})
        segment=first._segments()[0]
        raw=segment.read_bytes()
        assert raw.endswith(bytes((10,)))
        segment.write_bytes(raw[:-1])
        restarted=SegmentWAL(tmp_path,max_bytes=10000)
        rid2=await restarted.append({"symbol":"ETH","n":2})
        assert rid2>rid1
        assert restarted.recover()==[
            (rid1,{"symbol":"BTC","n":1}),
            (rid2,{"symbol":"ETH","n":2}),
        ]
        assert len(segment.read_bytes().splitlines())==2
    asyncio.run(run())


def test_corrupt_middle_record_blocks_replay_and_prevents_checkpoint_skip(tmp_path):
    async def run():
        w=SegmentWAL(tmp_path,max_bytes=10000)
        a=await w.append({"n":1})
        b=await w.append({"n":2})
        c=await w.append({"n":3})
        segment=w._segments()[0]
        rows=segment.read_text(encoding="utf-8").splitlines()
        tampered=json.loads(rows[1])
        tampered["payload"]={"n":999}
        rows[1]=json.dumps(tampered)
        segment.write_text(chr(10).join(rows)+chr(10),encoding="utf-8")
        with pytest.raises(ValueError,match="Corrupt WAL record"):
            list(w.iter_recover())
        with pytest.raises(ValueError,match="Corrupt WAL record"):
            SegmentWAL(tmp_path,max_bytes=10000)
        assert (a,b,c)==(1,2,3)
    asyncio.run(run())
