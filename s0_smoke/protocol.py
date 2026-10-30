"""Pure, bounded BTCUSDT public-market validation; no transport or trading code."""
from decimal import Decimal, localcontext
import re

MAX_SEEN_TRADES = 100_000
MAX_BATCH = 1024
MIN_MS = 1451606400000
MAX_MS = 4102444800000
_NUMBER = re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', re.ASCII)


def _integer(value, name, low=0, high=2**63-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid ' + name)
    return value


def _time(value, now):
    _integer(value, 'timestamp', MIN_MS, MAX_MS)
    if not now - 30_000 <= value <= now + 5_000:
        raise ValueError('timestamp outside freshness window')
    return value


def _number(value):
    if type(value) is not str or len(value) > 48 or not _NUMBER.fullmatch(value):
        raise ValueError('invalid numeric string')
    number = Decimal(value)
    if not Decimal('0') < number <= Decimal('1000000000000000000') or number.as_tuple().exponent < -18:
        raise ValueError('number out of bounds')
    return number


def _canonical(value):
    result = format(value, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def _keys(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError('invalid object keys')


class MarketState:
    def __init__(self):
        self._seen = {}
        self._stats = dict(trade_count=0, buy_count=0, sell_count=0, duplicate_trades=0,
                           book_updates=0, duplicate_books=0, connections=1, reconnects=0)
        self._buy = Decimal(0)
        self._sell = Decimal(0)
        self._book = None
        self._trade_seq = None
        self._last_book_ts = None
        self._last_trade_ts = None

    def reconnect(self):
        self._book = None
        self._trade_seq = None
        self._last_book_ts = None
        self._stats['connections'] += 1
        self._stats['reconnects'] += 1

    def summary(self):
        return dict(self._stats, buy_volume=_canonical(self._buy), sell_volume=_canonical(self._sell),
                    best_bid=_canonical(self._book[2]) if self._book else None,
                    best_ask=_canonical(self._book[4]) if self._book else None,
                    last_book_ts=self._last_book_ts, last_trade_ts=self._last_trade_ts)

    def ingest(self, message, now_ms):
        _integer(now_ms, 'now_ms', MIN_MS, MAX_MS)
        _keys(message, ('topic', 'type', 'ts', 'data'), ('cts',))
        ts = _time(message['ts'], now_ms)
        if message['type'] != 'snapshot':
            raise ValueError('snapshot required')
        if 'cts' in message and _time(message['cts'], now_ms) > ts + 1000:
            raise ValueError('cts after envelope')
        topic = message['topic']
        if topic == 'orderbook.1.BTCUSDT':
            self._ingest_book(message['data'], ts)
            kind = 'book'
        elif topic == 'publicTrade.BTCUSDT':
            self._ingest_trades(message['data'], ts, now_ms)
            kind = 'trades'
        else:
            raise ValueError('unsupported topic')
        return {'kind': kind, 'summary': self.summary()}

    def _ingest_book(self, data, ts):
        _keys(data, ('s', 'b', 'a', 'u', 'seq'))
        if data['s'] != 'BTCUSDT':
            raise ValueError('wrong symbol')
        u = _integer(data['u'], 'update id', 1)
        seq = _integer(data['seq'], 'sequence')
        sides = []
        for name in ('b', 'a'):
            side = data[name]
            if type(side) is not list or len(side) != 1 or type(side[0]) is not list or len(side[0]) != 2:
                raise ValueError('L1 requires exactly one price and quantity per side')
            sides.extend((_number(side[0][0]), _number(side[0][1])))
        if sides[0] >= sides[2]:
            raise ValueError('crossed book')
        current = (u, seq, *sides)
        duplicate = False
        if self._book:
            if ts < self._last_book_ts:
                raise ValueError('book timestamp regressed')
            if u != 1 and (u < self._book[0] or seq < self._book[1]):
                raise ValueError('book ordering regressed')
            if u == self._book[0]:
                if current != self._book:
                    raise ValueError('changed duplicate book')
                duplicate = True
        self._stats['duplicate_books' if duplicate else 'book_updates'] += 1
        self._book = current
        self._last_book_ts = ts

    def _ingest_trades(self, data, ts, now):
        if type(data) is not list or not 1 <= len(data) <= MAX_BATCH:
            raise ValueError('invalid trade batch size')
        pending = {}
        records = []
        previous_seq = self._trade_seq
        previous_timestamp = None
        for trade in data:
            _keys(trade, ('T', 's', 'S', 'v', 'p', 'i'), ('BT', 'RPI', 'seq', 'L'))
            if trade['s'] != 'BTCUSDT' or trade['S'] not in ('Buy', 'Sell'):
                raise ValueError('invalid trade symbol or side')
            timestamp = _time(trade['T'], now)
            if previous_timestamp is not None and timestamp < previous_timestamp:
                raise ValueError('trade batch timestamp regressed')
            previous_timestamp = timestamp
            if timestamp > ts + 1000:
                raise ValueError('trade after envelope')
            identity = trade['i']
            if type(identity) is not str or not 1 <= len(identity) <= 128 or not identity.isascii() or not all(33 <= ord(c) <= 126 for c in identity):
                raise ValueError('invalid trade id')
            price, volume = _number(trade['p']), _number(trade['v'])
            for key in ('BT', 'RPI'):
                if key in trade and type(trade[key]) is not bool:
                    raise ValueError('invalid trade flag')
            if 'L' in trade and trade['L'] not in ('PlusTick', 'ZeroPlusTick', 'MinusTick', 'ZeroMinusTick'):
                raise ValueError('invalid tick direction')
            seq = _integer(trade['seq'], 'trade sequence') if 'seq' in trade else None
            fingerprint = (timestamp, trade['S'], price, volume, trade.get('BT'), trade.get('RPI'), seq, trade.get('L'))
            old = pending.get(identity, self._seen.get(identity))
            if old is not None and old != fingerprint:
                raise ValueError('conflicting duplicate trade')
            duplicate = old is not None
            if seq is not None and not duplicate:
                if previous_seq is not None and seq < previous_seq:
                    raise ValueError('trade sequence regressed')
                previous_seq = seq
            pending[identity] = fingerprint
            records.append((duplicate, trade['S'], volume, timestamp))
        if len(self._seen) + len(pending.keys() - self._seen.keys()) > MAX_SEEN_TRADES:
            raise ValueError('trade dedup capacity exhausted; stop required')
        # All validation precedes mutation. Higher precision keeps bounded decimals exact.
        with localcontext() as context:
            context.prec = 80
            for duplicate, side, volume, timestamp in records:
                if duplicate:
                    self._stats['duplicate_trades'] += 1
                    continue
                self._stats['trade_count'] += 1
                self._stats['buy_count' if side == 'Buy' else 'sell_count'] += 1
                if side == 'Buy':
                    self._buy += volume
                else:
                    self._sell += volume
                self._last_trade_ts = max(self._last_trade_ts or timestamp, timestamp)
        self._seen.update(pending)
        self._trade_seq = previous_seq
