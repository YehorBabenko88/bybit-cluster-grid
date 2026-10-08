"""Per-topic monotonic receipt watchdog, independent of exchange timestamps."""


class TopicWatchdog:
    def __init__(self, symbols, started_at, timeout_seconds=120.0):
        self.timeout_seconds=float(timeout_seconds)
        self.last_seen={symbol:float(started_at) for symbol in symbols}

    def observe(self, symbol, now):
        if symbol in self.last_seen:
            self.last_seen[symbol]=float(now)

    def stalled(self, now):
        return [
            symbol for symbol, last in self.last_seen.items()
            if float(now)-last>self.timeout_seconds
        ]
