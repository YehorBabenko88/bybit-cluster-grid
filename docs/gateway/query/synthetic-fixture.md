# Fixed synthetic immutable byte closure

decode_synthetic_fixture(manifest_bytes,objects_by_sha256) is a pure locally
consistent fixture decoder. Five already-read dependency objects plus root are
bounded before hashing: root16KiB, each dependency at most512KiB, total1MiB.
Role-specific limits are descriptor4KiB, index/dependencies16KiB, rows/coverage
512KiB. Exact closed C3, one segment, max1440 rows and minute cells, exact hashes/
lengths/counts/lineage/schema joins and explicit coverage matching are checked.
Decimal string OHLCV values remain exact; no numeric output conversion occurs.

Result is detached data labeled SYNTHETIC_FIXTURE_LOCALLY_CHECKED_ONLY, actual
provider coverage/gaps UNKNOWN, publication/registry UNPROVEN and no execution
authority. Decoder is not the A4 manifest authority or a registry/proof adapter.
Future actual read path must also invoke the admitted A4 decode_manifest codec.

Fixture preimages in tests/gateway_query/fixtures are the exact Root/A4 ACKed
review1 objects. Root SHA8d216a8bc1117c240ef45d96b57f415779a14e7ee438dcf5c4109d3826b8b719;
row descriptor14c9f8e8d5c70584b0ca675c6de676498dafedab442076e71c96d45eb4346a77.
Two rows at0/120000 and an EXPLICIT GAP60000; never infer source absence or feed
the full gapped window to a contiguous Meta research adapter.

Actual ObjectStore tests use explicit GATEWAY_A4_SOURCE_ROOT, exact Unified
f9f2d04595cf2360dab78980996ae6c34c9e26fc/tree7fa3c8ad67c4efece7e2a692f48fb63a9e40ffd3,
all primary physical files compared to unreplaced Git blobs before import and
after tests, no extra files/cache admitted. Missing source capsule produces an
explicit skip/NOT_RUN, never actual-store PASS; dedicated qualification must set
the exact source and require0skip. Tests create only owned TemporaryDirectory
fixtures, use actual ObjectStore put/read/open and actual manifest codec, and
exercise missing/corrupt bytes. These are NOT authenticated query tests.

Primary source hashes are ObjectStore193c4e68e48dcdda212412ed7bd00d23afa04fe36bffb84c074948602bb8f739,
manifest43f7eb6961248d7ec21e4f2ab0d4e2c0e70876590d590ccd7cf18b934c9605e1.
Physical CRLF hashes are not interchangeable primary source admission.

No positive query API exists yet. Approved proposed owner ABI requires trusted
expected_identity_authority and fixed DisposableIdentityAuthority.require_issued_read
before each of six reads and final bounded output (query7); manifest2 is separate.
Complete output cap1MiB, no truncation. Root-qualified exact A2 source/dependencies/
actual disposable mTLS/store/registry/grant/audit composition and cross-owner
evidence remain required before positive query integration. Existing P0/F06 unchanged.
