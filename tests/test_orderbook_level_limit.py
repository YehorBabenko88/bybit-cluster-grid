import pytest

from grid.orderbook import parse_book_levels


def test_orderbook_frame_level_limit_rejects_oversized_input():
    levels=[[str(100+i),"1"] for i in range(201)]
    with pytest.raises(ValueError,match="level limit"):
        parse_book_levels(levels,snapshot=True)


def test_orderbook_frame_level_limit_allows_valid_depth_50():
    levels=[[str(100+i),"1"] for i in range(50)]
    parsed=parse_book_levels(levels,snapshot=True)
    assert len(parsed)==50


def test_orderbook_frame_level_limit_applies_to_deltas():
    levels=[[str(100+i),"0"] for i in range(201)]
    with pytest.raises(ValueError,match="level limit"):
        parse_book_levels(levels)
