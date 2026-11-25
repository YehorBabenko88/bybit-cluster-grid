"""Bybit orderbook snapshot/delta state with fail-closed sequence validation."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
import re
from market_math import wall_notional, book_summary_metrics

@dataclass
class OrderBook:
    symbol: str
    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    asks: dict[Decimal, Decimal] = field(default_factory=dict)
    update_id: int | None = None
    sequence: int | None = None
    valid: bool = False
    max_levels: int = 500

    def __post_init__(self):
        if type(self.symbol) is not str or re.fullmatch('[A-Z0-9]{2,30}', self.symbol) is None:
            raise ValueError('invalid orderbook instrument')
        if type(self.max_levels) is not int or not 1 <= self.max_levels <= 500:
            raise ValueError('invalid orderbook depth bound')

    def reset(self):
        self.bids.clear()
        self.asks.clear()
        self.update_id = None
        self.sequence = None
        self.valid = False

    def apply(self, message: dict):
        if not isinstance(message, dict) or not isinstance(message.get("data"), dict):
            self.reset()
            return False
        data = message["data"]
        if data.get("s") != self.symbol:
            self.reset()
            return False
        kind = message.get("type")
        uid = data.get("u")
        seq = data.get("seq")
        if type(uid) is not int or type(seq) is not int or not 0 <= uid < 2**63 or not 0 <= seq < 2**63:
            self.reset()
            return False
        if kind == "snapshot":
            self.reset()
            try:
                self._levels(data)
            except (ValueError, TypeError, ArithmeticError):
                self.reset()
                return False
            self.update_id = uid
            self.sequence = seq
            self.valid = self._healthy()
            if not self.valid:
                self.reset()
            return self.valid
        if kind != "delta" or not self.valid or self.update_id is None or self.sequence is None:
            self.reset()
            return False
        # Bybit may skip update IDs in streamed messages; require strictly
        # increasing update IDs and cross-sequence, not falsely assume +1.
        if uid <= self.update_id or seq <= self.sequence:
            self.reset()
            return False
        try:
            self._levels(data)
        except (ValueError, TypeError, ArithmeticError):
            self.reset()
            return False
        self.update_id = uid
        self.sequence = seq
        self.valid = self._healthy()
        if not self.valid:
            self.reset()
        return self.valid

    def _levels(self, data):
        for field, book in (("b",self.bids),("a",self.asks)):
            levels = data.get(field, [])
            if type(levels) is not list or len(levels) > self.max_levels:
                raise ValueError('bounded orderbook levels required')
            seen = set()
            for level in levels:
                if type(level) not in (tuple, list) or len(level) != 2:
                    raise ValueError('invalid orderbook level shape')
                price_text, size_text = level
                if any(type(value) not in (str, int, float, Decimal) or len(str(value)) > 160
                       for value in (price_text, size_text)):
                    raise ValueError('invalid orderbook numeric representation')
                price, size = Decimal(str(price_text)), Decimal(str(size_text))
                wall_notional(price, size)  # Math owns finite/sign/exponent/coefficient bounds.
                if price in seen:
                    raise ValueError('duplicate orderbook price')
                seen.add(price)
                if size == 0:
                    book.pop(price,None)
                else:
                    book[price]=size
            if len(book) > self.max_levels:
                raise ValueError('orderbook depth cap exceeded')

    def _healthy(self):
        if not self.bids or not self.asks:
            return False
        try:
            # No independent spread/notional or price comparison engine.
            book_summary_metrics(self.bids, self.asks, Decimal(1))
        except (ValueError, ArithmeticError):
            return False
        return True
