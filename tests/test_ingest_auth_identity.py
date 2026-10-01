from grid.coordinator import constant_time_equal
from grid.resources import NODE_ID
from grid.storage import ingest_headers


def test_constant_time_equal_handles_mismatched_lengths():
    assert constant_time_equal("abc", "abc")
    assert not constant_time_equal("abc", "abcd")
    assert not constant_time_equal("", "secret")
    assert not constant_time_equal(None, "secret")


def test_ingest_headers_use_canonical_node_id():
    headers = ingest_headers()
    assert headers["X-Node-ID"] == NODE_ID
    assert headers["X-Node-ID"]
