import asyncio
import json
import zlib

import pytest

from grid.segment_wal import SegmentWAL


@pytest.mark.parametrize("bad_id", [True, 1.0, "1", -1])
def test_wal_rejects_noncanonical_record_ids(tmp_path, bad_id):
    payload={"symbol":"BTCUSDT"}
    body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode()
    row={"id":bad_id,"crc32":zlib.crc32(body)&0xffffffff,"payload":payload}
    (tmp_path/"wal-00000000000000000001.seg").write_text(json.dumps(row)+"\n")
    with pytest.raises(RuntimeError,match="corrupt WAL record"):
        SegmentWAL(tmp_path)


@pytest.mark.parametrize("bad_crc", [True, 1.0, "123", -1, 4294967296])
def test_wal_rejects_noncanonical_crc(tmp_path, bad_crc):
    row={"id":1,"crc32":bad_crc,"payload":{"symbol":"BTCUSDT"}}
    (tmp_path/"wal-00000000000000000001.seg").write_text(json.dumps(row)+"\n")
    with pytest.raises(RuntimeError,match="corrupt WAL record"):
        SegmentWAL(tmp_path)
