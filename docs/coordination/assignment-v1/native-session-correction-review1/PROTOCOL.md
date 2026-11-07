# Native Consul session identifier correction — scoped successor review1

Old review2 packet/lease schema50da8f32 remain unchanged. NEW lease schema
9bdb1084004fcc6cfb76fa0f1bce0013b6a26a9b288cbb71c82db621feb4f4d0
changes ONLY worker_session_id's native identifier type, plus schema/version IDs
and its new definition. All actor/client/job/realm/lease/attempt UUIDv4 rules
remain unchanged; no casefold, normalization, rekey, arbitrary string or None.

## Actual observation and provenance

Own pinned Consul1.22.2 Windows binary SHA41762ef5b98c8dd9b6852df6cfbceed37e7f0acc5760856be33100f1092475e1,
three actual voters with ACL defaultdeny; genuine per-run mTLS service certificate.
Actual real HTTP response from /v1/session/create:
`{"ID":"cee8705d-033c-168f-2d94-3dfd00149167"}` status200.
Actual session/info and KV Session, KV Value.session_id and source session ID all
equal EXACTLY that unchanged string. Native lock ModifyIndex30. Full raw response,
session/info and canonical KV Value bytes in actual-native-session.json;
SHA bd1c5976812e09a1585cabff995a9454330da165a436dc6c0053a526785426fe.
ACL credentials/keys/PEM are excluded. Actual client observed loaded server DER.
Principal-session primitive only, no issued job/Assignment/resource hold.

That native ID has no RFC UUIDv4 version (uuid.UUID(...).version is None). Existing
Core ConsulSessionAuthority already validates canonical UUID without forcing4.
New broker wrongly reused client UUIDv4 validator: actual first native suite had
four errors at that parser. Split `_native_session` from `_uuid`; exact same actual
native flow now passes. Original failing logs retained, no old-source rewrite.

## Exact native syntax and authority boundary

Native ID: string length36, ASCII lowercase hex groups8-4-4-4-12, strict full end,
and runtime str(uuid.UUID(value)) == value. No imposed version/variant bits;
actual Consul Session API + actual matching KV Session/index checks establish
existence/current ownership. Syntax alone returns NO context/permit/authority.
No all-string/substring/null acceptance; preserve exact server bytes/case.
Schema delta paths: /$id, /$defs/native_session_id,
/properties/schema/const, /properties/worker_session_id/$ref. Nothing else.

Schema vector: actual old native ID rejected by old schema; accepted by successor;
8 malformed/noncanonical negatives rejected;4 unchanged client UUIDv4 fields
reject that native ID. Those are structural controls, not native authority tests.
Actual owner broker tests separately cover native policy CAS rejection/no effect,
destroyed session, foreign REAL session rebound under original key, and real
one-of-three quorum loss. No mocked success/leasebool or fake issued record seeds.
Working suite12/0skip is WIP until source-bound exact HEAD qualification/review;
do not transfer it into schema/A5/A4 counts or native job admission.

## Required joint freeze and gates

Request A5/A4/Root exact scoped ACK of this native identifier correction only.
Future actual runtime plan builder must select successor schema hash and recalc
full exact native payload; old operation/byte examples are not automatically a
new encoded hash proof. Current broker/API/source implementation and native
principal provisioning require independent exact qualification.
Public job submit/dispatch remains DENY; strict UTC-at-commit, actual worker
capacity/containment, two admitted failure domains/publication and production/
physical gates remain P0. READ source84093865 unchanged.
