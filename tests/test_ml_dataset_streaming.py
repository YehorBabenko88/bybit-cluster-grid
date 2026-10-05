from pathlib import Path

def test_dataset_builder_streams_in_bounded_batches():
    s=Path("grid/ml_dataset_builder.py").read_text()
    assert ".cursor(" in s
    assert "prefetch=self.batch_size" in s
    assert "members=[];payloads=[]" in s
    assert "rows=await self.pool.fetch" not in s
    assert "selected=[" not in s
    assert "manifest=[" not in s

def test_dataset_hash_is_incremental_and_ordered():
    s=Path("grid/ml_dataset_builder.py").read_text()
    assert "ORDER BY event_ts,sample_id" in s
    assert 'digest.update(b"\\n")' in s
    assert "digest.update(payload_hash.encode())" in s
