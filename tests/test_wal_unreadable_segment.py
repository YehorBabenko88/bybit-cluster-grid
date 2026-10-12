import asyncio
from unittest.mock import patch

import pytest

from grid.segment_wal import SegmentWAL


def test_unreadable_segment_blocks_recovery(tmp_path):
    async def scenario():
        wal = SegmentWAL(tmp_path)
        await wal.append({"minute": 1})
        segment = wal._segments()[0]
        original_open = open

        def failing_open(path, *args, **kwargs):
            if str(path) == str(segment) and args and args[0] == "rb":
                raise PermissionError("simulated WAL read failure")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=failing_open):
            with pytest.raises(RuntimeError, match="cannot read WAL segment"):
                wal.recover()
            with pytest.raises(RuntimeError, match="cannot read WAL segment"):
                SegmentWAL(tmp_path)

    asyncio.run(scenario())
