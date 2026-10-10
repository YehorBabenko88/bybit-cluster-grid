from grid.segment_wal import SegmentWAL


def test_checkpoint_rejects_malformed_and_negative_values(tmp_path):
    wal = SegmentWAL(tmp_path)
    for value in ("-1", "1junk", "1 2", "", "１２", "1.0"):
        wal.checkpoint.write_text(value, encoding="utf-8")
        assert wal._read_checkpoint(wal.checkpoint) is None


def test_checkpoint_accepts_ascii_decimal(tmp_path):
    wal = SegmentWAL(tmp_path)
    wal.checkpoint.write_text("123\n", encoding="ascii")
    assert wal._read_checkpoint(wal.checkpoint) == 123


def test_corrupt_non_ascii_primary_falls_back_to_backup(tmp_path):
    wal = SegmentWAL(tmp_path)
    wal.checkpoint.write_bytes(bytes([255, 254, 0]))
    wal.checkpoint_backup.write_text("7", encoding="ascii")
    assert wal._read_checkpoint(wal.checkpoint) is None
    assert wal._checkpoint_id() == 7
