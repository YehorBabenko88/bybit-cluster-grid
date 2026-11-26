# Grid B / C / D: qualified PARTIAL read contract v1 (candidate)

**Status: CONTRACT CANDIDATE, NO_GO.** PR #300, stacked on Grid B #299.
The sole validator now lives at `market_data_v2/qualified_read_contract.py`; the
historical `grid/qualified_read_contract.py` is only a compatibility import alias.
The additive `market_data_v2` SDK is distributed with the *existing* Market Data
wheel, not with a new exchange client or an independent service. It
does **not** alter the immutable 49-module `market_data` v1.1 package or sealed
902-node test roster. An independent approved SDK re-anchor and consumer switch
must precede canonical distribution or production route activation.

## Separation of evidence

- `record_integrity=VERIFIED` means exact deterministic SHA256 and closed
  source-record shape/Math-domain validation succeeded on supplied read rows.
  It does **not** authenticate the exchange, Bybit origin or trusted machine.
- `source_authenticity=NOT_INDEPENDENTLY_ATTESTED`, always.
  `source_identity_verified=True` inside an earlier record is merely the
  producer's admitted callback equality check; hashes are not signatures.
- `exchange_completeness=NOT_ATTESTED` and `coverage.missing_minutes`
  represent only the selected minute interval, not all possible Bybit trades.
- `quality_attestation=NOT_INDEPENDENTLY_ATTESTED` is independent of both
  hash/Math integrity and coverage. `source_declared_quality` contains exactly
  the source-declared status labels (potentially `INVALID`).
- `immutable=False`, `storage_immutability=NOT_ATTESTED`:
  a pure validator cannot establish PostgreSQL role/trigger/WAL custody.
  Agent C must produce a separately trusted, scoped database receipt.
- `execution_authority=False`, `trading_authorized=False` always. D can
  show explicitly labeled provisional data but must not automatically enable
  a paper strategy or real trading based on `PARTIAL` alone.

## Candidate payload fields

`schema=market_data.qualified-read-envelope.v1`,
`api_version={major:1,minor:1}`, `producer=market_data`,
`symbol`, `timeframe=1m`, `status`, `reason`,
`record_integrity`, `source_authenticity`, `exchange_completeness`,
`source_declared_quality`, `quality_attestation`, `coverage`,
`freshness_utc_ms`, `source_revision`, `producer_epoch`,
`dataset_fingerprint`, `rows`, `immutable`, `storage_immutability`,
`execution_authority`, `trading_authorized`.

Accepted result states:

- `PARTIAL / EXCHANGE_COMPLETENESS_UNATTESTED`: all supplied source minute
  records are structurally/Math valid, no requested-minute gap, same source
  epoch, and latest event clock within the 120-second freshness window.
  Exchange-wide coverage and independent origin still unknown.
- `GAP / MISSING_MINUTES_OR_EPOCH_CHANGE`: missing intervals or divergent
  epoch/source identity/revision. Rows remain read-only for diagnostics.
- `STALE / FRESHNESS_WATERMARK_EXPIRED`: as-of clock exceeds last provider
  event by more than 120 seconds. Rows diagnostic only.
- `UNAVAILABLE / SOURCE_PROVENANCE_UNAVAILABLE`: at least one source record
  itself is `UNAVAILABLE`; envelope rows empty.
- Any malformed, rehashed false completeness, forged authority, malformed
  epoch, duplicate revision, invalid OHLC/footprint, future event/ingestion
  clock, nonfinite amount or symbol mismatch: hard rejection
  `ProvenanceReadError` (no qualified envelope).

**Important integration blocker:** Grid legacy `grid/provenance.py` writes
`producer=bybit-cluster-grid`, while canonical
`market_data/provenance.py` writes `producer=market_data`.
The new contract accepts **only canonical** market_data v1.1 records.
C's lab PostgreSQL migration 47 may use legacy Grid fixtures; these must
not be relabeled or rehashed to claim canonical provenance. Agree on an
explicit, source-bound migration/reader adapter and canonical writer first.

## C and D acceptance requests

C: pin the actual canonical Grid migration SHA, verify read-only PostgreSQL
18 role and source-row immutable receipt separately, protect write grants,
prove duplicate revisions and corrupt hash refusal, and return exact source
schema/provenance receipt without untrusted status promotion.

D: accept a qualified `PARTIAL` **read/chart receipt** only under the
explicit contract, check source/content/availability and separate trusted
storage witness, and require independently approved strategy-level conditions
to authorize synthetic paper simulation. Reject `GAP`, `STALE`,
`UNAVAILABLE`, tampered and unsupported data for strategy input.
No production trading credentials or exchanges used in the test suite.

CI is an inert Linux/Windows Python 3.11–3.13 matrix pinned to
Math `9e6acbd9e12a91189f57234828e31640983af553`. Its
14 test methods use synthetic fixtures and never open a network connection,
create PostgreSQL services or trade. A queued workflow is **not** a PASS.

## Round 3 additive managed HTTP route / SDK (not yet qualified E2E)

- **New route:** `GET /internal/v2/candles/qualified?symbol=BTCUSDT&limit=1[&before_ms=...]`.
  Query parameters have closed keys, strictly numeric bounded page size 1–1000,
  timestamp cursor in positive int64, and no implicit symbol or limit default.
  This uses canonical Data49 `market_data.history_api.immutable_minutes`
  (PostgreSQL READ ONLY repeatable-read query) and the same canonical
  `market_data.provenance.minute_record` record bytes. No Grid legacy producer
  alias is accepted.
- **Authenticated managed entrypoint:**
  `market_data_v2.read_api.main(startup_admission=RootProvidedAdmission)`
  replaces the existing `market_data.history_api.main` handler on the **same
  loopback port**. It subclasses that handler to preserve all old v1 paths and
  ingress limits, requires a current `UNIFIED_MODULE_ID=market_data` startup
  admission and the exact `Bearer UNIFIED_INSTANCE_TOKEN` before SQL read,
  then rechecks admission both immediately before and after the read.
  Its advertised console script rejects unmanaged startup. Root E owns the
  process/service handoff and must prove **old listener quiescence before launch**.
  No server instance was started by this PR or by this report.
- **Response:** `schema=market_data.qualified-read-envelope.v1`, outer
  `api_version={major:2,minor:0}`, inner source-records remain v1.1.
  `read_only=True`, `paper_admitted=False`, `execution_authority=False`,
  `trading_authorized=False`, `storage_immutability=NOT_ATTESTED`, always.
  Unknown row -> `UNAVAILABLE` with empty array. A genuine observed record
  may be `PARTIAL` but **never** `AVAILABLE`. A malformed source is HTTP
  503, not a 400 blamed on the caller; invalid query syntax is HTTP 400.
  No source payload, bearer, DSN or exception text is exposed in error replies.
- **Compatibility:** no v1.1 bytes in `market_data/*` were edited; existing
  sealed 902-node roster remains unchanged. A separately tested, additive
  `market_data_v2` SDK package is included by the existing `market-data`
  wheel with a distinct opt-in entrypoint. Existing v1 routes are **not
  automatically retargeted**. D must explicitly consume new DTO and perform
  its own Root-admitted read/chart validation. C must independently attest
  PostgreSQL row custody, proper producer and non-bypassable writer fencing.
- **Hosted CI contract:** Linux/Windows, Python 3.11/3.12/3.13 with pinned
  Math `9e6acbd9e12a91189f57234828e31640983af553`, tests the
  actual new wheel `python -I` import and both the existing 14 contract test
  methods and 10 read-route/revocation cases. This is synthetic and does not
  prove physical PG18, Bybit provider identity, legacy worker exclusion,
  source-wheel bootstrap or production availability.

### Exact C / D / E handoff questions

1. **C**: please pin canonical PostgreSQL `provenance_minutes` migration and
   writer/reader role, report current schema identity and enforced resource-side
   fencing token (monotone, non-bypassable by old `grid` writer). Supply a
   verified PG18 owner-only read receipt; avoid translating the legacy
   `bybit-cluster-grid` producer to canonical `market_data` by rehashing.
2. **D**: please implement a strict `market_data.qualified-read-envelope.v1`
   adapter alongside the existing v1.1 adapter **after reviewing this DTO**,
   gated by the same Root-managed capability. Preserve chart-only `PARTIAL`
   with distinct source/quality/coverage, never authorize paper trading.
3. **E**: please nominate the current Root-approved exact artifact + source pin
   and startup exclusion DTO; call **only** v2 replacement entrypoint after
   confirmed quiescent original listener, legacy WS/REST writers, and C's DB
   resource fence. Do not simply set `MARKET_DATA_PROVENANCE_READ=1` on old v1.

**No user database, service, source seal, current market listener, or trading
state was modified. CODE NO_GO / PRODUCTION NO_GO until positive/negative
cross-repository and native acceptance.**
