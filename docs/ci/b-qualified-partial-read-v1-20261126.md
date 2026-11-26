# Grid B / C / D: qualified PARTIAL read contract v1 (candidate)

**Status: CONTRACT CANDIDATE, NO_GO.** PR #300, stacked on Grid B #299.
This module is intentionally located at `grid/qualified_read_contract.py` and
does **not** alter the immutable 49-module `market_data` SDK package or sealed
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
