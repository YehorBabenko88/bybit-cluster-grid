from dataclasses import dataclass,asdict
import hashlib,json


@dataclass(frozen=True)
class TradePlan:
    symbol:str
    side:str
    entry:float
    stop_loss:float
    take_profit:float
    notional:float=100.0
    setup_type:str="UNKNOWN"
    signal_id:str|None=None

    def __post_init__(self):
        side=self.side.upper()
        if side not in ("LONG","SHORT"):raise ValueError("side must be LONG or SHORT")
        if min(float(self.entry),float(self.stop_loss),float(self.take_profit),float(self.notional))<=0:
            raise ValueError("trade plan values must be positive")
        if side=="LONG" and not (self.stop_loss<self.entry<self.take_profit):
            raise ValueError("LONG requires SL < entry < TP")
        if side=="SHORT" and not (self.take_profit<self.entry<self.stop_loss):
            raise ValueError("SHORT requires TP < entry < SL")

    @property
    def quantity(self):
        return float(self.notional)/float(self.entry)

    @property
    def fingerprint(self):
        raw=json.dumps(asdict(self),sort_keys=True,separators=(",",":"))
        return hashlib.sha256(raw.encode()).hexdigest()


def assert_plan_unchanged(original,current):
    if original.fingerprint!=current.fingerprint:
        raise RuntimeError("immutable trade plan changed after entry")
    return True
