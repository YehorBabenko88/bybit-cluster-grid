from pathlib import Path
import pytest
from grid.content_cache import ContentAddressedCache,sha256_file


def test_content_cache_deduplicates_and_materializes_verified_bytes(tmp_path):
    source=tmp_path/"source.bin";source.write_bytes(b"abc"*1000)
    cache=ContentAddressedCache(tmp_path/"cache")
    first=cache.put(source)
    second=cache.put(source,first["sha256"])
    assert first["created"] is True
    assert second["created"] is False
    assert cache.has(first["sha256"])
    out=tmp_path/"out.bin"
    cache.materialize(first["sha256"],out)
    assert out.read_bytes()==source.read_bytes()
    assert sha256_file(out)==first["sha256"]


def test_content_cache_rejects_wrong_expected_hash(tmp_path):
    source=tmp_path/"source.bin";source.write_bytes(b"payload")
    cache=ContentAddressedCache(tmp_path/"cache")
    with pytest.raises(ValueError,match="sha256 mismatch"):
        cache.put(source,"0"*64)


def test_content_cache_detects_corruption(tmp_path):
    source=tmp_path/"source.bin";source.write_bytes(b"payload")
    cache=ContentAddressedCache(tmp_path/"cache")
    item=cache.put(source)
    Path(item["path"]).write_bytes(b"corrupt")
    assert cache.has(item["sha256"]) is False
    with pytest.raises(ValueError,match="corruption"):
        cache.put(source)
