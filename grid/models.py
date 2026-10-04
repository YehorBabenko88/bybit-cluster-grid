from dataclasses import dataclass, field
from time import time

@dataclass
class Trade:
    symbol: str
    ts_ms: int
    price: float
    qty: float
    side: str
    trade_id: str = ""
    seq: int | None = None
    block_trade: bool = False
    rpi: bool = False
    system_ts_ms: int | None = None
    receive_ts_ms: int | None = None
    continuity_gap: bool = False

@dataclass
class PriceCluster:
    buy_qty: float = 0.0
    sell_qty: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    @property
    def volume(self): return self.buy_qty + self.sell_qty
    @property
    def delta(self): return self.buy_qty - self.sell_qty

@dataclass
class NodeState:
    node_id: str
    cpu_count: int
    cpu_pct: float
    ram_total: int
    ram_available: int
    disk_free: int
    assigned: list[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time)
