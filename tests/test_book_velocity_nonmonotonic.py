from grid.book_velocity import BookVelocity


def test_duplicate_and_backward_timestamps_do_not_fabricate_rates():
    velocity=BookVelocity()
    assert velocity.update("BTCUSDT",1000,{100:2},{101:3})["book_add_rate"] is None
    for ts in (1000,999):
        result=velocity.update("BTCUSDT",ts,{100:999},{101:3})
        assert all(value is None for value in result.values())
        assert velocity.state["BTCUSDT"][0]==1000
    result=velocity.update("BTCUSDT",2000,{100:4},{101:3})
    assert result["book_add_rate"]==2.0
    assert result["depth_change_rate"]==2.0


def test_independent_symbol_baselines():
    velocity=BookVelocity()
    velocity.update("BTCUSDT",1000,{100:1},{})
    assert velocity.update("ETHUSDT",1000,{100:1},{})["book_update_rate"] is None
    assert velocity.update("BTCUSDT",2000,{100:3},{})["book_add_rate"]==2.0
