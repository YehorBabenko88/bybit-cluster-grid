"""Pure bounded subscribe handshake; caller supplies monotonic seconds.

Public frames arriving before the ACK are frozen, never consumed as market
observations until a valid acknowledgement releases them in arrival order.
"""
from s0_smoke.policy import TOPICS, MAX_JSON, canonical, load_json


class SubscriptionGate:
    MAX_FRAMES = 8
    MAX_BYTES = 2 * 1024 * 1024
    ACK_SECONDS = 2

    def __init__(self, now):
        self._clock(now)
        self._started = now
        self._last = now
        self._acknowledged = False
        self._failed = False
        self._pending = []
        self._bytes = 0

    @property
    def acknowledged(self):
        return self._acknowledged

    @staticmethod
    def _clock(now):
        # The bound excludes NaN/infinity and preserves sub-second precision.
        if type(now) not in (int, float) or not 0 <= now <= 10**12:
            raise ValueError('S0_SUBSCRIPTION_CLOCK_BLOCKED')

    def check(self, now):
        try:
            if self._failed:
                raise ValueError('S0_SUBSCRIPTION_BLOCKED')
            self._clock(now)
            if now < self._last:
                raise ValueError('S0_SUBSCRIPTION_CLOCK_REGRESSION')
            if not self._acknowledged and now - self._started > self.ACK_SECONDS:
                raise ValueError('S0_SUBSCRIPTION_ACK_TIMEOUT')
            self._last = now
        except ValueError:
            self._failed = True
            raise

    def feed(self, value, now):
        self.check(now)
        try:
            if type(value) is not dict:
                raise ValueError('S0_SUBSCRIPTION_OBJECT_BLOCKED')
            # Validate and freeze JSON before retaining any caller-owned reference.
            try:
                raw = canonical(value)
                if len(raw) > MAX_JSON:
                    raise ValueError('S0_SUBSCRIPTION_FRAME_LIMIT')
                frozen = load_json(raw)
            except (TypeError, ValueError, OverflowError, RecursionError):
                raise ValueError('S0_SUBSCRIPTION_JSON_BLOCKED') from None
            if 'topic' in frozen:
                if frozen['topic'] not in TOPICS or 'op' in frozen:
                    raise ValueError('S0_SUBSCRIPTION_TOPIC_BLOCKED')
                if self._acknowledged:
                    return [frozen]
                if len(self._pending) >= self.MAX_FRAMES or self._bytes + len(raw) > self.MAX_BYTES:
                    raise ValueError('S0_SUBSCRIPTION_BUFFER_LIMIT')
                self._pending.append(raw)
                self._bytes += len(raw)
                return []
            operation = frozen.get('op')
            if operation == 'subscribe':
                if self._acknowledged:
                    raise ValueError('S0_SUBSCRIPTION_DUPLICATE_ACK')
                if frozen.get('success') is not True or frozen.get('req_id') != 'S0':
                    raise ValueError('S0_SUBSCRIPTION_ACK_BLOCKED')
                ready = [load_json(frame) for frame in self._pending]
                self._pending.clear()
                self._bytes = 0
                self._acknowledged = True
                return ready
            if operation in ('ping', 'pong'):
                if frozen.get('req_id', 'S0') != 'S0':
                    raise ValueError('S0_SUBSCRIPTION_CONTROL_BLOCKED')
                return []
            raise ValueError('S0_SUBSCRIPTION_OPERATION_BLOCKED')
        except ValueError:
            self._failed = True
            raise
