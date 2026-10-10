import asyncio

from grid.segment_wal import SegmentWAL


def test_valid_unterminated_last_record_is_separated_from_next_append(tmp_path):
    async def scenario():
        wal = SegmentWAL(tmp_path)
        assert await wal.append({"minute": 1}) == 1
        segment = wal._segments()[-1]
        raw = segment.read_bytes()
        assert raw.endswith(bytes([10]))
        segment.write_bytes(raw[:-1])

        restored = SegmentWAL(tmp_path)
        assert [rid for rid, _ in restored.recover()] == [1]
        assert await restored.append({"minute": 2}) == 2

        again = SegmentWAL(tmp_path)
        assert [rid for rid, _ in again.recover()] == [1, 2]
        assert [payload["minute"] for _, payload in again.recover()] == [1, 2]

    asyncio.run(scenario())
