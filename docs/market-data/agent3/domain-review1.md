# Market domain binding review1

Implements exact schema/version/hash dispatch in `grid.market_ingestion_domain`.
This is executable input validation, not a runtime authority adapter or admitted
Control Mux data projection. No shared runtime or legacy adapter is modified.

Machine-readable units, scale, grammar, lineage and raw schema pins are in
`tests/fixtures/agent3-market-domain/registry.json`. Review4's 27 manifest members
were verified against unreplaced Git objects at Unified
`360c5cdc9dae88416d69f8765f3dff5ab8828945`; A1/A6 scoped ACKs bind its exact manifest
and schema. This check is not independent reexecution of their models.

Supported parse domains:

- `bybit.instrument-identity.v1`: exact exchange/category/symbol/instrument_version.
  Version is a positive dimensionless u63 incarnation counter, never allocated by
  the parser. Markets, delist/relist incarnations and symbol case cannot merge.
  Schema plus executable range check rejects values above 9223372036854775807.
- `unified.historical-checkpoint.v3-review1`: delegates to the frozen existing V3
  codec, retaining its raw schema SHA and complete canonical claim bytes.
  COMMITTED remains an untrusted claim. COMMIT_UNCONFIRMED exposes no invented
  dataset/instrument/partition lineage. Unknown time never implies unknown commit.

All integer values remain canonical decimal strings. Timestamp/cursor fields use
the frozen checkpoint UTC milliseconds and exact range/cursor semantics. No
financial price/volume domain is admitted by this slice; its units/scale cannot
be guessed. No legacy number conversion, truncation, normalization or root reuse.
The claim digest is explicitly SHA256 of complete claim bytes and must never be
passed as a manifest, publication or authorized-view root.

Unknown domain/version or wrong schema binding raises `DomainUnavailable` for an
integration layer to map to UNAVAILABLE. Invalid known-domain bytes raise
`DomainFormatError`. Frozen results contain immutable bytes; even manually forged
result objects cannot gain authority because `require_authoritative_domain`
always denies. Real authorized projection requires separately admitted A2/A4
consistent-read, receipt, manifest and disclosure checks. A4 has confirmed no
actual commit/reconcile/read-manifest seam is currently available; none is faked.

Retirement and unsubscription do not delete history. Existing retired-history
safeguard remains intact. No migrations, storage writes, provider calls or
listeners occur here. Dataset manifests/publication/integrity/progress domains
remain UNAVAILABLE until their exact owner contract and runtime seam are admitted.

Local tests cover exact binding, identity separation, hostile/canonical input,
unconfirmed lineage and unconditional authority denial. These are CODE/CLAIM
checks, not ENDPOINT, Windows service, crash durability or physical acceptance.
Rollback removes only the additive module/tests/fixtures/document.
