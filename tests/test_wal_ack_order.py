import asyncio

import pytest

from grid.segment_wal import SegmentWAL


def test_ack_cannot_skip_earlier_unprocessed_record(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        first=await wal.append({"minute":1})
        second=await wal.append({"minute":2})
        with pytest.raises(ValueError,match="oldest pending"):
            await wal.ack(second)
        assert wal._checkpoint_id()==0
        assert [rid for rid,_ in wal.recover()]==[first,second]
        await wal.ack(first)
        await wal.ack(second)
        assert wal.recover()==[]

    asyncio.run(scenario())
