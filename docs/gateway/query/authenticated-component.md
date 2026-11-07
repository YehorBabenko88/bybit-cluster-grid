# Actual disposable synthetic query component

query_market_data(request_bytes, *, owner_read_capability,
expected_identity_authority, pinned_owned_store) implements only the isolated
component authorized by Root after exact owner profile/source ACKs. It owns no
listener, Gateway route, PKI factory, provider client or storage implementation.
Root's public HTTP resource routes require separate integration/admission.

Root must qualify a SINGLE canonical source/dependency composition before import:
A2 identity2cb6b21eac5617ff39ad7a96b7e1c73118e0af00/treef51a4a976c2864a584446c3a5c11e8bfcbcca537,
gateway_identity.py raw84093865e8477ef6562100d41137922785446c9cb4e024c9ba7105593a2b36c1;
A4 storage/manifestf9f2d04595cf2360dab78980996ae6c34c9e26fc/tree7fa3c8ad67c4efece7e2a692f48fb63a9e40ffd3.
Module names, arbitrary sys.path providers or a client role are not source admission.
The function consumes actual Root-owned classes/issuer/store from that composition.
It is not a sandbox against arbitrary hostile Python in the trusted process.

Exact admitted DisposableIdentityAuthority and GatewayReadCapability types are
required, with independent trusted expected_identity_authority. Every boundary
calls fixed DisposableIdentityAuthority.require_issued_read(expected,cap,...),
never cap-selected issuer/callback. Binding uses dataset/local revision, exact
manifest root, ROW schema, consumer/view UUID and full original request digest.
GETmanifest has its distinct schema/tool/bytes/capability. Missing handles/source
yield NOT_EXECUTED/null rows; invalid actual handles raise closed owner refusal.

Six reads root/descriptor/index/rows/coverage/dependencies each have a preceding
current check; a seventh immediately precedes bounded return. Each actual read
uses the lesser of per-object cap and remaining1MiB. Actual A4 decode_manifest
consumes already-read bytes, so no seventh read is hidden. Pure fixture decoder
checks the complete exact hash-bound closure. Query/root identity/revision/schema
joins and explicit coverage range are checked. Output rows/cells are restricted
to the requested aligned range and final-candle-end event cutoff; no latest or
missing-history substitution. Complete encoded output capped independently1MiB.

Result schema grid.gateway.synthetic-query-result.v1-review1 retains complete
original request/digest, dataset/manifest revisions and root, selected string rows
and explicit fixture cells. SYNTHETIC_QUERY_RESULT and SYNTHETIC_SESSION_AUTHENTICATED_ONLY
never imply native authentication, Consul publication, verified registry/provider
coverage, replica proof, historical PIT, L3/book availability, orders or finances.
Actual provider coverage/gaps UNKNOWN and publication/registry UNPROVEN remain
explicit even when generated fixture coverage is locally consistent.

## Executed component tests

Actual pinned A2 TLSFixture creates per-test disposable CA/certs, actual accepted
server SSLSocket and client-observed server DER pin, no public fake cap factory.
Actual ObjectStore stores immutable owned bytes. Twelve query tests cover six
reads/seven checks, bounded row+gap/full-window output, no-handle zero attribute
IO, legit foreign issuer/same store, wrong view/range/cut digest, wrong actual store,
wrong manifest tool capability, real revocation before IO and after sixth read,
actual elapsed expiry, and missing dependency refusal. Test read instrumentation
wraps actual store IO; it does not substitute authority/current checks.

Explicit source roots are mandatory for this suite; otherwise skip means NOT_RUN,
not actual query PASS. Source qualification must require zero skips. Owner primary
files are compared to unreplaced Git blobs before imports and after, and reject
extra files/Python caches/native overlays. Only owned TemporaryDirectory data,
loopback sockets/threads and PKI are created/cleaned. No PEM/key output is retained.

Own isolated runtime venv uses the exact Windows hash lock in this directory:
cryptography46.0.3/cffi2.0.0/pycparser2.23, installed offline with --require-hashes
--only-binary=:all: from actual owner wheels. Global Python unchanged. Local
component PASS does not prove hosted Windows CI, production crypto or complete
Gateway route acceptance. Retained historical schemas/P0/F06 remain unchanged.
