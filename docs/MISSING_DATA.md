# Missing / partial market data

Missing data is a state, not an exception.

Every symbol/feed is classified independently as:
- available
- missing
- stale
- unsupported
- degraded
- unknown

Examples:
- dated futures may have no funding rate -> UNSUPPORTED, not ERROR
- ticker delta omits unchanged fields -> retain last known field value
- pre-launch contract may have no order book -> MISSING/UNSUPPORTED until continuous trading
- delisted instrument may return an empty book -> clear local book and mark unavailable
- temporary OI delay -> OI STALE while trades/footprint continue

## Analysis rule
Never invent a zero for unavailable data.

`OI = 0` and `OI unavailable` are different facts.

Feature records must include:
- data completeness score
- feed availability flags
- stale flags
- age of last observation

A strategy may specify mandatory and optional inputs. Missing optional confirmation lowers confidence/completeness but does not crash collection. Missing mandatory inputs skips only that setup for that symbol/time window.

## ML rule
Future training datasets must preserve missingness flags. Do not silently forward-fill indefinitely and do not convert missing values to zero. Models can then learn only from explicitly controlled imputations or from samples meeting a minimum completeness threshold.
