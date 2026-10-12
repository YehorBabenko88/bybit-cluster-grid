import asyncio

import pytest

from grid.segment_wal import SegmentWAL


def test_ack_rejects_unallocated_ids_without_advancing_checkpoint(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        first=await wal.append({"minute":1})
        with pytest.raises(ValueError,match="outside the allocated"):
            await wal.ack(first+10)
        with pytest.raises(ValueError,match="outside the allocated"):
            await wal.ack(-1)
        with pytest.raises(ValueError,match="outside the allocated"):
            await wal.ack(True)
        assert wal._checkpoint_id()==0
        assert wal.recover()==[(first,{"minute":1})]
        await wal.ack(first)
        assert wal.recover()==[]

    asyncio.run(scenario())
