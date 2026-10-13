import asyncio
import json
import zlib

from grid.segment_wal import SegmentWAL


def test_startup_repairs_torn_tail_without_reading_entire_segment(tmp_path, monkeypatch):
    payload={"symbol":"BTCUSDT"}
    body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode()
    record=json.dumps({"id":1,"crc32":zlib.crc32(body)&0xffffffff,"payload":payload}).encode()+b"\n"
    path=tmp_path/"wal-00000000000000000001.seg"
    records=b''.join(json.dumps({"id":i,"crc32":zlib.crc32(body)&0xffffffff,"payload":payload}).encode()+b"\n"
                     for i in range(1,4001))
    path.write_bytes(records+b'{"id":4001,"crc32":')
    import builtins
    original_open=builtins.open
    class LimitedReader:
        def __init__(self, file):self.file=file
        def __enter__(self):self.file.__enter__();return self
        def __exit__(self,*args):return self.file.__exit__(*args)
        def __getattr__(self,name):return getattr(self.file,name)
        def read(self,size=-1):
            assert size>=0 and size<=65536, "unbounded startup read"
            return self.file.read(size)
    def limited_open(file,mode="r",*args,**kwargs):
        result=original_open(file,mode,*args,**kwargs)
        if str(file)==str(path) and mode=="rb+":
            return LimitedReader(result)
        return result
    monkeypatch.setattr(builtins,"open",limited_open)
    wal=SegmentWAL(tmp_path)
    assert wal._next_id==4001
    assert path.read_bytes()==records
