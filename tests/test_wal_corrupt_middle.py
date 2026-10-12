import asyncio

import pytest

from grid.segment_wal import SegmentWAL


def test_corrupt_middle_record_blocks_recovery_instead_of_skipping(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        await wal.append({"minute":1})
        await wal.append({"minute":2})
        await wal.append({"minute":3})
        path=wal._segments()[-1]
        lines=path.read_bytes().splitlines(keepends=True)
        lines[1]=b'{"id":2,"crc32":0,"payload":{"minute":2}}\n'
        path.write_bytes(b"".join(lines))
        with pytest.raises(RuntimeError,match="corrupt WAL record"):
            SegmentWAL(tmp_path)

    asyncio.run(scenario())


def test_corrupt_final_complete_line_blocks_recovery(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        await wal.append({"minute":1})
        path=wal._segments()[-1]
        path.write_bytes(path.read_bytes()+b'not-json\n')
        with pytest.raises(RuntimeError,match="corrupt WAL record"):
            SegmentWAL(tmp_path)

    asyncio.run(scenario())
