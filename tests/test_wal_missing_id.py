import asyncio
import json
import zlib

import pytest

from grid.segment_wal import SegmentWAL


def test_ack_refuses_missing_record_id_after_checkpoint(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        first=await wal.append({"minute":1})
        second=await wal.append({"minute":2})
        third=await wal.append({"minute":3})
        await wal.ack(first)
        segment=wal._segments()[-1]
        lines=segment.read_bytes().splitlines(keepends=True)
        segment.write_bytes(lines[0]+lines[2])
        restarted=SegmentWAL(tmp_path)
        assert [rid for rid,_ in restarted.recover()]==[third]
        with pytest.raises(ValueError,match="missing record id"):
            await restarted.ack(third)
        assert restarted._checkpoint_id()==first
    asyncio.run(scenario())
