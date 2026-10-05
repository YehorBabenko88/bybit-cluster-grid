import json
from datetime import timedelta
from .features import FeatureEngine
from .volatility_regime import VolatilityRegimeDetector
from .setup_flags import setup_flags
from .retention_v2 import register_consumer
from .control_state import set_consumer_watermark

class UnifiedFeatureBuilder:
    """Builds one reproducible 1m feature row from candle + nearest prior microstructure."""
    def __init__(self,lookback=60,micro_max_age_s=5):
        self.engine=FeatureEngine(lookback)
        self.regime=VolatilityRegimeDetector(lookback=max(lookback,120))
        self.micro_max_age_s=int(micro_max_age_s)
        self.started=False

    async def start(self,pool):
        if self.started:return
        await register_consumer(pool,"market_events","unified_features",required=True,active=True)
        self.started=True

    async def build(self,pool,row):
        base=self.engine.on_candle(row)
        ts=row["ts"]; symbol=row["symbol"]
        book=await pool.fetchrow("""SELECT event_ts,payload FROM market_events
            WHERE symbol=$1 AND event_type='orderbook_snapshot'
              AND event_ts<=$2 AND event_ts>=$2-($3 * interval '1 second')
            ORDER BY event_ts DESC LIMIT 1""",symbol,ts,self.micro_max_age_s)
        deriv=await pool.fetchrow("""SELECT event_ts,payload FROM market_events
            WHERE symbol=$1 AND event_type='derivatives_ticker'
              AND event_ts<=$2 AND event_ts>=$2-($3 * interval '1 second')
            ORDER BY event_ts DESC LIMIT 1""",symbol,ts,self.micro_max_age_s)
        bp=_payload_dict(book["payload"]) if book else {}
        dp=_payload_dict(deriv["payload"]) if deriv else {}
        features=dict(base)
        features.update({
            "book_imbalance":_num(bp.get("imbalance")),
            "spread":_num(bp.get("spread")),
            "bid_depth":_num(bp.get("bid_depth")),
            "ask_depth":_num(bp.get("ask_depth")),
            "open_interest":_num(dp.get("open_interest")),
            "funding_rate":_num(dp.get("funding_rate")),
            "mark_price":_num(dp.get("mark_price")),
            "index_price":_num(dp.get("index_price")),
            "basis_rate":_num(dp.get("basis_rate")),
        })
        caps={"candle":True,"footprint":True,"orderbook":bool(book),"derivatives":bool(deriv)}
        # Candle/trade quality is a hard gate. Missing optional feeds remain explicit capabilities.
        eligible=bool(base["eligible"])
        regime=self.regime.update(symbol,features,eligible=eligible)
        features.update(regime)
        features.update(setup_flags(features,regime["regime"],eligible))
        return {"symbol":symbol,"ts":ts,"eligible":eligible,
                "quality_status":base["data_quality"],"regime":regime["regime"],
                "regime_score":regime["regime_score"],"features":features,"capabilities":caps}

    async def persist(self,pool,built):
        await pool.execute("""INSERT INTO market_features_1m(symbol,ts,eligible,quality_status,regime,regime_score,features,capabilities)
          VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb)
          ON CONFLICT(symbol,ts) DO UPDATE SET eligible=EXCLUDED.eligible,
          quality_status=EXCLUDED.quality_status,regime=EXCLUDED.regime,
          regime_score=EXCLUDED.regime_score,features=EXCLUDED.features,
          capabilities=EXCLUDED.capabilities,built_at=now()""",
          built["symbol"],built["ts"],built["eligible"],built["quality_status"],
          built["regime"],built["regime_score"],json.dumps(built["features"]),json.dumps(built["capabilities"]))
        # The raw microstructure window used for this minute is now durably
        # represented by market_features_1m; retention follows this consumer.
        # A crash before this monotonic
        # watermark only delays retention; it can never cause premature deletion.
        await set_consumer_watermark(
            pool,"market_events","unified_features",built["symbol"],built["ts"],required=True
        )

def _num(v):
    try: return float(v) if v is not None else None
    except (TypeError,ValueError): return None


def _payload_dict(value):
    """Normalize asyncpg JSON/JSONB payloads to a mapping without breaking ingestion."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed=json.loads(value)
        except (json.JSONDecodeError,TypeError,ValueError):
            return {}
        return parsed if isinstance(parsed,dict) else {}
    try:
        return dict(value)
    except (TypeError,ValueError):
        return {}
