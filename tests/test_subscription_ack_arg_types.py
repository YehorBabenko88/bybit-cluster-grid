import pytest
from grid import microstructure

@pytest.mark.parametrize("bad_args", ["abc", 123, [None], {"x": "y"}])
def test_invalid_ack_args_shape_is_not_a_valid_topic_list(bad_args):
    assert not (isinstance(bad_args, list) and all(isinstance(x, str) for x in bad_args))
