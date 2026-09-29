PILOT_SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT")

def guarded_live_symbols(*,market_enabled,install_mode,live_mode,node_assignments,instrument_symbols):
    """Fail-closed market assignment policy."""
    if not market_enabled:
        return []

    if install_mode=="NORMAL" and live_mode=="NORMAL":
        return list(node_assignments)

    if install_mode=="PILOT" and live_mode=="PILOT_VALIDATING":
        available=set(instrument_symbols)
        return [symbol for symbol in PILOT_SYMBOLS if symbol in available][:5]

    return []
