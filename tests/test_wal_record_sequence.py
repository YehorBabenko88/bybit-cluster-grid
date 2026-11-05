"""Metadata corruption must not turn an acknowledged ID into a lost payload."""
import asyncio
import json

import pytest

from grid.segment_wal import SegmentWAL

NODES = ('LS5', 'PC1', 'PC2', 'PC3', 'PC4', 'LS7')
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT',
           'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT')


@pytest.mark.parametrize('across_segments', [False, True])
@pytest.mark.parametrize('checkpoint', [0, 2])
@pytest.mark.parametrize('replacement', [1, 2])
@pytest.mark.parametrize('tail', ['terminated', 'unterminated', 'torn'])
def test_duplicate_or_regressive_ids_block_recovery_without_mutation(
        tmp_path, across_segments, checkpoint, replacement, tail):
    async def scenario():
        wal = SegmentWAL(tmp_path, segment_bytes=1 if across_segments else 65536)
        for index, symbol in enumerate(SYMBOLS):
            await wal.append({'node': NODES[index % 6], 'symbol': symbol})
        # Alter only ID metadata: payload CRC remains fully valid. Put the
        # duplicate/regression inside or across a physical segment boundary.
        segments = wal._segments()
        if across_segments:
            target = segments[2]
            records = [json.loads(target.read_bytes())]
            records[0]['id'] = replacement
        else:
            target = segments[0]
            records = [json.loads(raw) for raw in target.read_bytes().splitlines()]
            records[2]['id'] = replacement
        target.write_bytes(b''.join(json.dumps(row).encode() + b'\n' for row in records))
        last = segments[-1]
        if tail == 'unterminated':
            last.write_bytes(last.read_bytes()[:-1])
        elif tail == 'torn':
            last.write_bytes(last.read_bytes() + b'{"id":11,"crc32":')
        # Model an existing durable checkpoint without invoking compaction.
        # Corrupt records <= checkpoint must still be inspected, not filtered.
        if checkpoint:
            wal.checkpoint.write_text(str(checkpoint), encoding='ascii')
        (tmp_path / 'checkpoint.next').write_bytes(b'3')
        (tmp_path / 'checkpoint.backup.next').write_bytes(b'2')
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        with pytest.raises(RuntimeError, match='corrupt WAL record'):
            SegmentWAL(tmp_path)
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
        # Also reject corruption introduced after this owner was constructed.
        with pytest.raises(RuntimeError, match='corrupt WAL record'):
            list(wal.iter_recover())
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    asyncio.run(scenario())


def test_retained_sequence_may_start_above_one_after_compaction(tmp_path):
    async def scenario():
        wal = SegmentWAL(tmp_path)
        for index, symbol in enumerate(SYMBOLS):
            await wal.append({'node': NODES[index % 6], 'symbol': symbol})
        path = wal._segments()[0]
        lines = path.read_bytes().splitlines(keepends=True)
        # Model an already compacted acknowledged prefix without deleting files.
        path.write_bytes(b''.join(lines[5:]))
        wal.checkpoint.write_text('5', encoding='ascii')
        restarted = SegmentWAL(tmp_path)
        assert [rid for rid, _ in restarted.iter_recover()] == list(range(6, 11))
        assert await restarted.append({'symbol': 'BTCUSDT'}) == 11
    asyncio.run(scenario())
