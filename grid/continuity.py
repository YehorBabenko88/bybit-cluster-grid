import time

class SequenceGuard:
    """Tracks exchange sequence continuity and forces resnapshot after a detected gap."""
    def __init__(self):
        self.last_seq=None
        self.last_update=None
        self.valid=False
        self.gaps=0

    def snapshot(self,seq=None,update_id=None):
        seq=_int(seq); update_id=_int(update_id)
        if seq is None or update_id is None or seq<0 or update_id<0:
            self.valid=False
            self.last_seq=None
            self.last_update=None
            return False
        # Replayed snapshots must not roll back an already valid book.
        # Bybit update_id=1 explicitly signals a book/service restart.
        if self.valid and update_id!=1 and (
            (self.last_seq is not None and seq<=self.last_seq)
            or (self.last_update is not None and update_id<=self.last_update)
        ):
            return False
        self.last_seq=seq
        self.last_update=update_id
        self.valid=True
        return True

    def delta(self,seq=None,update_id=None):
        seq=_int(seq); update_id=_int(update_id)
        if not self.valid:
            return False
        if seq is None or update_id is None or seq<0 or update_id<0:
            self.valid=False; self.gaps+=1
            return False
        # Bybit cross-sequence is global across orderbook levels and symbols:
        # it must increase, but consecutive values are not guaranteed here.
        # A jump alone does not prove a missing per-symbol delta.
        if seq is not None and self.last_seq is not None and seq<=self.last_seq:
            self.valid=False; self.gaps+=1
            return False
        if update_id is not None and self.last_update is not None and update_id<=self.last_update:
            self.valid=False; self.gaps+=1
            return False
        self.last_seq=seq if seq is not None else self.last_seq
        self.last_update=update_id if update_id is not None else self.last_update
        return True

def _int(v):
    try: return int(v)
    except (TypeError,ValueError,OverflowError): return None

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
