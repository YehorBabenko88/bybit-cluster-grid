# Grid read-only market DTO v2

`GET /v2/candles` and `GET /v2/footprint` accept `symbol` and `limit` and return a JSON object with `version: 2`, `symbol`, `timeframe: "1m"`, `provenance` and `rows`. The legacy URL paths `/v1/candles` and `/v1/footprint` are aliases with the same v2 response and must be treated as such by callers. The instruments and node DTOs retain version 1.

Market NUMERIC values are fixed-point decimal strings with their stored scale or JSON null when the underlying column is nullable. Consumers must not parse them as binary64 for transport or calculation. The integer `t` is Unix milliseconds in UTC and is limited to the safe JSON integer range. Rows with a timestamp outside that contract fail closed. `trades` is an integer or null.

Candle rows retain stored `quality_status` and `quality_reasons`. Older schemas without quality columns produce `UNKNOWN` and an empty reason list. Provenance identifies the serving owner, persisted table and time encoding. It does not attest the underlying exchange events.

Footprint pagination is a bounded display snapshot. The envelope marks exchange completeness as unattested, including on an empty result. `coverage.row_limit_reached` means at least one additional row exists. A non-null `coverage.partial_bucket_t` identifies a minute split by the cap. Consumers must not use truncated or unattested snapshots as complete input to research.
