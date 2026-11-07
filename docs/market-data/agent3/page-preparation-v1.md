# Offline historical page preparation v1

`grid.market_page_validation.prepare_kline_page` is a pure component for extending
the existing Grid backfill adapter. It is not connected to a worker, provider or
database. ROOT explicitly deferred changes to `market_backfill.py` until legacy
fetch/store impact review; that existing file remains unchanged.

Provider specification verified 2026-11-07:
https://bybit-exchange.github.io/docs/v5/market/kline

The documented maximum is1000 rows, reverse ordered by startTime, seven string
columns. For linear contracts, volume is base coin and turnover is quote coin;
open-candle close is provisional. This component does not determine trusted
provider time or candle finality. Actual provider time eligibility and API budget
remain separate blocked admission gates. Offline fixtures are not actual Bybit
ingestion or ten-instrument historical acceptance.

## Exact representation and bounds

Version: `bybit.linear.kline.1m.fixed-decimal.v1`. Only canonical composite identity
with category `linear` is supported. Range is aligned half-open UTC Unix
milliseconds `[start_ms,end_ms)` with string u63 endpoints. Input row is
`[startTime,open,high,low,close,volume,turnover]`, exactly7 strings; timestamp is
canonical u63 decimal, minute-aligned, in range. Prices are positive quote/base;
volume nonnegative base; turnover nonnegative quote. No guessed inverse units.
Price must satisfy low<=open/close<=high. Decimal input grammar is
`[0-9]+(?:\.[0-9]+)?`, max80 characters per financial value. Output removes only
leading integer zeroes and trailing fractional zeroes, preserving exact value.
No exponent/sign/nonfinite/float/rounding/implicit old-domain conversion.

At most1000 rows, never truncation. `raw_rows_bytes` is compact JSON of decoded
exchange row strings, preserving all duplicate/string spellings. It is not the
original HTTP response image; future transport must retain that independently.
`normalized_rows_bytes` is compact JSON of exact normalized string rows, reverse
ordered, economically identical duplicates collapsed. Conflicting duplicates
reject the whole page. Each image has its own SHA256; digest identifies only its
bytes, never instrument ownership, a segment manifest, publication or view root.
Instrument identity and requested range remain separate immutable result fields.

## Gaps and cursor

Missing intervals between observations and the requested upper boundary remain
explicit `suspected_gaps` with aligned half-open endpoints. Empty pages retain
the entire interval as suspected. These are recoverable candidates, not proof of
source absence or unrecoverability. Older tail is `unobserved_before_ms`; pagination
does not justify marking that tail complete. Neither short nor empty page proves
history complete. Candidate next end is oldest observed timestamp minus1 (null at
requested lower bound or when empty). It must never advance a durable checkpoint
without actual atomic data/manifest/gap disposition publication. In particular,
publication cannot silently skip these suspected interior gaps.

All results say `PREPARED_UNCOMMITTED`, contain no committed cursor, completion
flag, authority receipt or publication root. Retry prepares the same bytes; it
does not supply durable idempotency, crash recovery or authority. Those require
actual A2/A4 seams, currently absent. Existing checkpoint/retention/legacy code is
unchanged. Rollback removes only this helper and its own tests/docs.
