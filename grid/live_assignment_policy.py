PILOT_SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT")

def pilot_universe(instrument_symbols):
    """Return the bounded live-canary universe; ownership is assigned by CONTROL."""
    available=set(instrument_symbols)
    return [symbol for symbol in PILOT_SYMBOLS if symbol in available][:5]

def guarded_live_symbols(*,market_enabled,install_mode,live_mode,node_assignments,instrument_symbols):
    """Fail-closed market assignment policy.

    Scheduler ownership is authoritative in both NORMAL and PILOT_VALIDATING.
    PILOT merely restricts the eligible universe; it must never replicate the
    whole pilot set to every pilot node.
    """
    if not market_enabled:
        return []

    assigned=list(node_assignments or [])
    available=set(instrument_symbols)

    if install_mode=="NORMAL" and live_mode=="NORMAL":
        return [symbol for symbol in assigned if symbol in available]

    if install_mode=="PILOT" and live_mode=="PILOT_VALIDATING":
        allowed=set(pilot_universe(instrument_symbols))
        return [symbol for symbol in assigned if symbol in allowed]

    return []
