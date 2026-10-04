import time

class SequenceGuard:
    """Validate Bybit order-book continuity.

    Cross-sequence (seq) and update ID (u) must move forward, but Bybit's
    public contract does not promise that every observed u differs by exactly
    one. TCP/WebSocket ordering plus a fresh snapshot after reconnect is the
    recovery boundary; u=1 is handled by the caller as a reset snapshot.
    """
    def __init__(self):
        self.last_seq=None
        self.last_update=None
        self.valid=False
        self.gaps=0
        self.stale=0
        self.last_reason=None

    def snapshot(self,seq=None,update_id=None):
        self.last_seq=_int(seq)
        self.last_update=_int(update_id)
        self.valid=True
        self.last_reason=None
        return True

    def delta(self,seq=None,update_id=None):
        seq=_int(seq); update_id=_int(update_id)
        self.last_reason=None
        if not self.valid:
            self.last_reason="awaiting_snapshot"
            return False

        # seq can jump forward; only backwards seq proves stale/out-of-order data.
        if seq is not None and self.last_seq is not None and seq < self.last_seq:
            self.stale+=1
            self.last_reason="stale_seq"
            return False

        if update_id is not None and self.last_update is not None:
            if update_id <= self.last_update:
                self.stale+=1
                self.last_reason="stale_update_id"
                return False

        self.last_seq=seq if seq is not None else self.last_seq
        self.last_update=update_id if update_id is not None else self.last_update
        return True

def _int(v):
    try: return int(v)
    except (TypeError,ValueError): return None

class TradeContinuity:
    """Public trades have no guaranteed contiguous sequence; track observability, not fake completeness."""
    def __init__(self,gap_ms=5000):
        self.gap_ms=int(gap_ms); self.last_ts=None; self.reconnects=0; self.suspect_gaps=0

    def reconnect(self):
        self.reconnects+=1

    def observe(self,ts_ms):
        ts=_int(ts_ms) or int(time.time()*1000)
        suspect=self.last_ts is not None and ts-self.last_ts>self.gap_ms
        if suspect: self.suspect_gaps+=1
        self.last_ts=max(ts,self.last_ts or ts)
        return suspect
