import builtins
import pytest

from grid.segment_wal import SegmentWAL


def test_startup_fails_closed_when_active_wal_tail_cannot_be_opened(tmp_path, monkeypatch):
    segment=tmp_path/"wal-00000000000000000001.seg"
    segment.write_bytes(b'{"id":1')
    original_open=builtins.open

    def failing_open(file,mode="r",*args,**kwargs):
        if str(file)==str(segment) and mode=="rb+":
            raise PermissionError("WAL file locked")
        return original_open(file,mode,*args,**kwargs)

    monkeypatch.setattr(builtins,"open",failing_open)
    with pytest.raises(RuntimeError,match="cannot inspect or repair WAL tail"):
        SegmentWAL(tmp_path)
    assert segment.read_bytes()==b'{"id":1'
