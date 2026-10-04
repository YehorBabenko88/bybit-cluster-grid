from grid.bybit import parse_public_trade,BybitProtocolError
import pytest


def test_public_trade_parser_accepts_current_bybit_shape():
    x=parse_public_trade({"T":1,"s":"BTCUSDT","S":"Buy","v":"0.01","p":"50000",
                          "i":"trade-1","seq":123,"BT":False,"RPI":True},"BTCUSDT")
    assert x["trade_id"]=="trade-1" and x["seq"]==123 and x["rpi"] is True


@pytest.mark.parametrize("item",[
    {"T":1,"s":"ETHUSDT","S":"Buy","v":"1","p":"1"},
    {"T":1,"s":"BTCUSDT","S":"Other","v":"1","p":"1"},
    {"T":1,"s":"BTCUSDT","S":"Buy","v":"0","p":"1"},
    {"T":1,"s":"BTCUSDT","S":"Buy","v":"1","p":"nan"},
])
def test_public_trade_parser_rejects_corrupt_or_cross_symbol_data(item):
    with pytest.raises(BybitProtocolError):
        parse_public_trade(item,"BTCUSDT")
