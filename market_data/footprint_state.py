"""Event-time/dedup/finalization lifecycle around canonical Math arithmetic.

No strategy or independent numeric implementation. The explicit first-seen POC
tie policy preserves the source lifecycle contract; price bins use canonical
Decimal HALF_EVEN, preserving the source tie policy without float division.
"""
from decimal import Decimal
from .numeric_dto import binary64
from .public_trades import Trade
import re

from market_math import (price_bucket, footprint_cell_update, exact_sum,
                                 executed_volume_delta, volume_profile_poc, wall_notional)


class FootprintBuilder:
    def __init__(self, tick_size, interval_s=60, finalization_delay_ms=0,
                 *, max_open_buckets=1024, max_trades_per_bucket=100000):
        self.tick_size = Decimal(str(tick_size))
        price_bucket(self.tick_size, self.tick_size)
        if type(interval_s) is not int or not 1 <= interval_s <= 604800:
            raise ValueError('invalid interval')
        if type(finalization_delay_ms) is not int or not 0 <= finalization_delay_ms <= 86400000:
            raise ValueError('invalid finalization delay')
        if type(max_open_buckets) is not int or not 1 <= max_open_buckets <= 1024:
            raise ValueError('invalid bucket cap')
        if type(max_trades_per_bucket) is not int or not 1 <= max_trades_per_bucket <= 1000000:
            raise ValueError('invalid event cap')
        self.interval_ms = interval_s * 1000
        self.finalization_delay_ms = finalization_delay_ms
        self.max_open_buckets = max_open_buckets
        self.max_trades_per_bucket = max_trades_per_bucket
        self.buckets = {}
        self.finalized_through_ms = {}

    def add(self, trade):
        # Freeze the complete canonical DTO before any Math owner can run.
        # No original event field is reread during admission or commit.
        if type(trade) is not Trade:
            raise ValueError('exact canonical Trade required')
        symbol, timestamp, microseconds, trade_id, side, price, quantity = (
            trade.symbol, trade.ts_ms, trade.ts_us, trade.trade_id,
            trade.side, trade.price, trade.qty)
        if (type(symbol) is not str or re.fullmatch('[A-Z0-9]{2,30}', symbol) is None
                or type(timestamp) is not int or not 0 <= timestamp <= 2**53 - 1
                or type(microseconds) is not int or not 0 <= microseconds <= 2**63 - 1
                or microseconds // 1000 != timestamp
                or type(trade_id) is not str or not 0 < len(trade_id) <= 128
                or type(side) is not str or side not in ('Buy', 'Sell')
                or type(price) is not Decimal or type(quantity) is not Decimal):
            raise ValueError('invalid literal execution snapshot')
        start = timestamp // self.interval_ms * self.interval_ms
        if symbol not in self.finalized_through_ms and len(self.finalized_through_ms) >= self.max_open_buckets:
            raise ValueError('instrument cap')
        if start <= self.finalized_through_ms.get(symbol, -1):
            return False
        key = (symbol, start)
        bucket = self.buckets.get(key)
        if bucket is not None and trade_id and trade_id in bucket['seen_trade_ids']:
            return False
        if bucket is None and len(self.buckets) >= self.max_open_buckets:
            raise ValueError('open bucket cap')
        if bucket is not None and bucket['trades'] >= self.max_trades_per_bucket:
            raise ValueError('event cap')
        level_price = price_bucket(price, self.tick_size, rounding="half_even")
        prior = bucket['levels'].get(level_price) if bucket else None
        if bucket is not None and prior is None and len(bucket['levels']) >= 20000:
            raise ValueError('price bucket cap')
        zero = Decimal(0)
        buy, sell = footprint_cell_update(prior['buy'] if prior else zero,
                                         prior['sell'] if prior else zero, quantity, side)
        total_buy, total_sell = footprint_cell_update(bucket['buy'] if bucket else zero,
            bucket['sell'] if bucket else zero, quantity, side)
        turnover = exact_sum((bucket['turnover'] if bucket else zero, wall_notional(price, quantity)))
        if bucket is None:
            bucket = dict(turnover=zero, open=price, high=price, low=price, close=price, buy=zero, sell=zero,
                trades=0, levels={}, seen_trade_ids=set(), first_event_ms=timestamp,
                last_event_ms=timestamp, quality_status='GOOD', quality_reasons=[])
            self.buckets[key] = bucket
        if trade_id:
            bucket['seen_trade_ids'].add(trade_id)
        if timestamp < bucket['first_event_ms']:
            bucket['open'] = price
        if timestamp >= bucket['last_event_ms']:
            bucket['close'] = price
        bucket['first_event_ms'] = min(bucket['first_event_ms'], timestamp)
        bucket['last_event_ms'] = max(bucket['last_event_ms'], timestamp)
        bucket['high'] = max(bucket['high'], price)
        bucket['low'] = min(bucket['low'], price)
        bucket['buy'], bucket['sell'] = total_buy, total_sell
        bucket['turnover'] = turnover
        bucket['trades'] += 1
        bucket['levels'][level_price] = dict(buy=buy, sell=sell,
            buy_count=(prior['buy_count'] if prior else 0) + int(side == 'Buy'),
            sell_count=(prior['sell_count'] if prior else 0) + int(side == 'Sell'))
        return True

    def mark_degraded(self, symbol, ts_ms, reason):
        start = ts_ms // self.interval_ms * self.interval_ms
        bucket = self.buckets.get((symbol, start))
        if bucket is not None:
            bucket['quality_status'] = 'DEGRADED'
            if reason not in bucket['quality_reasons']:
                bucket['quality_reasons'].append(reason)

    def mark_open_degraded(self, symbol, reason):
        for (instrument, start) in self.buckets:
            if instrument == symbol:
                self.mark_degraded(symbol, start, reason)

    def pop_closed(self, now_ms):
        output = []
        prepared = []
        for key, bucket in list(self.buckets.items()):
            symbol, start = key
            if start + self.interval_ms + self.finalization_delay_ms > now_ms:
                continue
            profile = {price: exact_sum((cell['buy'], cell['sell']))
                       for price, cell in bucket['levels'].items()}
            poc = volume_profile_poc(profile, tie_policy='first_seen')
            row = dict(symbol=symbol, start_ms=start,
                source_event_start_ms=bucket['first_event_ms'], source_event_end_ms=bucket['last_event_ms'],
                **{field: binary64(bucket[field]) for field in ('open', 'high', 'low', 'close')},
                buy_volume=binary64(bucket['buy']), sell_volume=binary64(bucket['sell']),
                delta=binary64(executed_volume_delta(bucket['buy'], bucket['sell'])),
                trade_count=bucket['trades'], poc_price=binary64(poc),
                turnover=binary64(bucket['turnover']),
                turnover_basis='EXECUTED_TRADE_PRICE_TIMES_QUANTITY_SUM',
                quality_status=bucket['quality_status'], quality_reasons=list(bucket['quality_reasons']),
                levels=[dict(price=binary64(price), buy_volume=binary64(cell['buy']),
                    sell_volume=binary64(cell['sell']),
                    delta=binary64(executed_volume_delta(cell['buy'], cell['sell'])),
                    volume=binary64(profile[price]), buy_count=cell['buy_count'], sell_count=cell['sell_count'])
                    for price, cell in sorted(bucket['levels'].items())])
            output.append(row)
            prepared.append(key)
        # No row is returned until every eligible DTO is representable. A
        # refusal in a later bucket must not erase an earlier unreturned row.
        for symbol, start in prepared:
            self.buckets.pop((symbol, start))
            self.finalized_through_ms[symbol] = max(start, self.finalized_through_ms.get(symbol, -1))
        return output
